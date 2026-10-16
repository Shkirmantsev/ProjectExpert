# 2026-10-04-context-enrichment Specification delta

Covers plan §3.4, §10, §10.1, §11, §11.1, §11.2.

## ADDED Requirements

### Requirement: explicit retrieval_text distinct from raw_text and metadata

The platform MUST maintain a strict distinction
between `raw_text` (the exact source text),
`retrieval_text` (the text actually passed to the
embedding model), and `metadata` (the exact filters,
provenance, version / security fields).

The `retrieval_text` MUST be built by a
`RetrievalTextBuilderPort` according to the rule
`retrieval_text = context_prefix + "\n\n" + raw_text`,
where `context_prefix` is built deterministically from
`document_title`, `heading_path`, `requirement_id` (when
semantically meaningful), `java_signature` (when
applicable), `protocol_name` (when applicable),
`caption`, and (optionally) a 1–3 sentence semantic
context produced by the `LocalContextualizer` behind
the opt-in `InferencePolicy`. The `retrieval_text` MUST
NOT embed absolute filesystem path, SHA, Git commit
hash, timestamp, bbox coordinates, security label, or
processing version.

#### Scenario: retrieval_text excludes forbidden fields

Given a chunk with an absolute path, a SHA, a Git
commit hash, a timestamp, a bbox, a security label,
and a processing version in its metadata
When the platform builds the `retrieval_text`
Then none of those fields appear in the embedding
input
And the chunk is still retrievable through the
existing filter, graph, and reranker pipeline.

#### Scenario: contextualizer output is not authoritative

Given an opt-in `LocalContextualizer` that returns a
proposed `requirement_id` for a chunk
When the platform builds the `retrieval_text`
Then the proposed `requirement_id` is NOT embedded
in the `retrieval_text`
And the authoritative `requirement_id` (from the
canonical knowledge) is used instead.

### Requirement: LocalContextualizer isolation

The platform MUST expose a `LocalContextualizer`
application service over the existing `LocalLLMPort`.
Its output is restricted to:

- 1–3 sentence semantic context;
- candidate entities;
- candidate relations;
- query aliases / glossary hints.

It is forbidden from producing authoritative metadata:
`requirement_id`, `protocol_version`, `validFrom`,
`validTo`, `security_class`, `git_revision`, `source_id`,
`license`. The outputs are tagged `INFERRED` or
`ASSUMPTION` and may never overwrite authoritative
metadata.

#### Scenario: local contextualizer is forbidden from producing IDs

Given a `LocalContextualizer` invocation
When the local LLM returns a proposed `requirement_id`
or `protocol_version`
Then the platform discards those fields
And the canonical `requirement_id` and
`protocol_version` are unchanged.

### Requirement: separate inference policy from source persistence policy

The platform MUST introduce a separate
`InferencePolicy` value object
(`NO_MODEL | LOCAL_MODEL_ALLOWED |
EXTERNAL_MODEL_ALLOWED`) and MUST NOT conflate it
with `SourcePersistencePolicy` (`LOCAL_ONLY | REFERENCE
| SNAPSHOT`). Both policies are evaluated by the
central Policy Engine
(`pi_platform/control/policy_engine.py`); a source
with `LOCAL_ONLY` persistence may still be processed
by a local model if the `InferencePolicy` is
`LOCAL_MODEL_ALLOWED` and the central Policy Engine
authorises it.

#### Scenario: source policy does not gate model exposure

Given a source with `SourcePersistencePolicy = LOCAL_ONLY`
and `InferencePolicy = LOCAL_MODEL_ALLOWED`
When the platform runs the local contextualizer
Then the local model sees the content
And the central Policy Engine records the
authorisation in the audit log.

### Requirement: contextualization cache key

The platform MUST cache local contextualisation with
the key
`sha256(chunk_content_hash || contextualizer_model_revision
|| prompt_version ||
enrichment_strategy_version)`. A Git branch switch MUST
reuse the result if the underlying content and strategy
are unchanged.

#### Scenario: branch switch reuses cached contextualization

Given a cached contextualization result for a
chunk + model + prompt + strategy
When the platform switches to a different Git branch
with the same chunk content and the same model
revision
Then the cached result is reused
And the platform does not re-invoke the local
contextualizer.

## MODIFIED Requirements

None. The existing context-enrichment `Requirements`
are extended additively; their bodies are not
rewritten.
