---
id: project.retrieval-evaluation-corpus
title: Retrieval evaluation corpus, baselines, and quality gates
kind: project
status: active
summary: Three-tier retrieval evaluation layout (evals/baselines/pre_change.json, evals/quality_gates.yaml, evals/corpus/, evals/reports/chunk_size_sweep.md) and CLI commands.
sourceRefs:
  - evals/baselines/pre_change.json
  - evals/quality_gates.yaml
  - evals/corpus/golden_queries.yaml
  - evals/reports/chunk_size_sweep.md
  - pi_platform/core/eval/retrieval_evaluator.py
  - scripts/eval_baseline.py
  - scripts/eval_retrieval.py
  - scripts/eval_chunk_size_sweep.py
maintenance:
  mode: authored
related:
  - modules.eval
  - adr.0026-embedding-profile-identity-and-vector-namespace
  - project.deployment-profiles
---

# Retrieval evaluation corpus, baselines, and quality gates

Change Packages I and J organise retrieval evaluation into three tiers:

1. **Tier 1 (deterministic CI baseline)** — `tests/test_retrieval_benchmark.py` and `evals/baselines/pre_change.json`, inspectable via `make eval-baseline` (`python3 scripts/eval_baseline.py show`).
2. **Tier 2 (local-model & PDF integration)** — `tests/test_tier2_local_model_integration.py` marked with `@pytest.mark.local_model`, `@pytest.mark.pdf`, and `@pytest.mark.slow` (registered in `pyproject.toml`), exercising 10/100/600-page generated PDF fixtures (`scripts/generate_pdf_fixtures.py`).
3. **Tier 3 (golden-query evaluation & chunk-size sweep)** — `project-intelligence eval retrieval` (`scripts/eval_retrieval.py`) and `project-intelligence eval chunk-size-sweep` (`scripts/eval_chunk_size_sweep.py`) over `evals/corpus/{synthetic,generated-pdf,multilingual,java,requirements}/` and `evals/corpus/golden_queries.yaml` (plus git-ignored `tmp/local/evals/` for confidential corpora). Thresholds for all 13 metrics are enforced from `evals/quality_gates.yaml`, and the chunk-size sweep is recorded in `evals/reports/chunk_size_sweep.md`.

[Eval module](../modules/eval.md) ·
[ADR 0026](../adr/0026-embedding-profile-identity-and-vector-namespace.md)
