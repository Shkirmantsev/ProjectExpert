---
id: adr.0010-hybrid-fusion-strategy
title: "ADR 0010: Phase 4 hybrid fusion strategy"
kind: adr
status: accepted
summary: Selected reciprocal rank fusion (RRF) as the default Phase 4 hybrid fusion strategy with k=60 and dense_weight=0.5 / sparse_weight=0.5; linear weighted sum is the documented fallback; learned fusion is deferred.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#27
  - project-intelligence-platform-architecture-v0.8.md#33
  - pi_platform/ports/retrieval/hybrid_retrieval.py
  - pi_platform/core/retrieval/hybrid_retrieval.py
  - openspec/specs/2026-10-04-hybrid-retrieval/spec.md
maintenance:
  mode: authored
---

# ADR 0010: Phase 4 hybrid fusion strategy

- Status: accepted
- Date: 2026-10-04
- Deciders: Phase 4 implementation change
- Source spec: [`2026-10-04-hybrid-retrieval`](../../../openspec/specs/2026-10-04-hybrid-retrieval/spec.md)
- Architecture baseline: [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  §27 (Hybrid Retrieval) and §33 (Retrieval-First Agent Access
  Strategy)

## Context

The §27 hybrid retrieval port composes the dense ANN, the
sparse BM25 and the exact-identifier lookup into a single
ranked candidate set. The fusion algorithm must be
replaceable through
`project-context.yaml:retrieval.fusion.strategy` and the
default strategy must be documented.

The platform records no labelled training data; the corpus
is the user's own project knowledge, which is too
heterogeneous to support a single learned fusion model.
The §33 retrieval-first escalation policy mandates a
deterministic, predictable ordering so the agent can reason
about the result. The multi-stage pipeline must be
reproducible across rerun (the §49 evaluation gate).

## Decision

Phase 4 ships **reciprocal rank fusion (RRF)** as the default
fusion strategy with `k=60` (the Cordonnier et al. 2020 /
Cormack et al. 2009 standard) and `dense_weight=0.5,
sparse_weight=0.5` defaults. The RRF score for a hit at
rank `r` is `weight / (k + r)`; the final score is the
sum of the RRF scores across the dense and sparse streams.

The strategy is replaceable through
`project-context.yaml:retrieval.fusion.strategy`. The
supported strategies are:

- `rrf` (default) — the documented decision.
- `linear` — linear weighted sum (`dense_weight * dense_score
  + sparse_weight * sparse_score`). The documented fallback
  for corpora where the RRF rank-1 tie-breaking is
  undesirable.

The active strategy is recorded in the hybrid port's
`stats()` response so the §49 evaluation fixture can assert
the active configuration.

## Alternatives considered

- **Learned fusion** (a binary classifier that scores
  candidate pairs as relevant / not relevant) — rejected
  because the platform has no labelled training data and
  the per-corpus calibration would require an explicit
  per-project training step that violates the
  retrieval-first escalation principle. The RRF default
  is unsupervised and works out of the box.
- **Linear weighted sum without per-corpus calibration** —
  the documented `linear` fallback; rejected as the
  default because the absolute scores of the dense ANN
  and the BM25 sparse index live on different scales and
  the linear sum is sensitive to the per-corpus score
  distribution. RRF is score-agnostic and uses rank only.
- **CombMNZ / CombSUM / Borda count** — considered; not
  selected because the §49 evaluation fixture and the
  multi-stage pipeline telemetry expect a single fused
  score per hit and the RRF `1 / (k + r)` formulation
  matches the §27 "score is bounded between 0.0 and 1.0"
  scenario without re-scaling.

## Consequences

Positive:

- RRF is unsupervised, deterministic, and works out of the
  box across corpora with different score distributions.
- The `k=60` constant is the documented standard; the
  multi-stage pipeline and the §49 evaluation fixture
  reproduce the same ranking across rerun.
- The RRF `1 / (k + r)` formulation naturally bounds the
  score in `(0, 1]` so the `RetrievalHit.score` invariant
  in `pi_platform/ports/retrieval/hybrid_retrieval.py`
  holds without re-scaling.

Negative:

- RRF is rank-only; a candidate ranked #1 in the dense
  stream and a candidate ranked #50 in the sparse stream
  both contribute `1 / (k + r)` irrespective of their
  absolute scores. Operators who require per-stream score
  calibration can switch to the `linear` strategy through
  configuration.
- The default `dense_weight=0.5, sparse_weight=0.5` is a
  neutral starting point; operators who want to favour one
  stream over the other must re-tune the weights through
  configuration. The §49 evaluation fixture is the
  recommended calibration instrument.

## Compliance

- `python -m unittest tests.test_platform_phase4
  .HybridRetrievalTests -v` — passes; the `dense_weight`
  and `sparse_weight` parameters are honoured by the RRF
  and the linear strategies.
- `python -m pi_platform.cli retrieval-status` — reports
  the active fusion strategy.
