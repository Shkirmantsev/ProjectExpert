## MODIFIED Requirements

### Requirement: replaceable provider

The `EmbeddingModelPort` MUST be implementable by a default
multilingual CPU adapter and by alternative bindings of the same model
without leaking backend-specific details into the port surface. The active
adapter MUST be selected through
`project-context.yaml:embedding.backend` configuration.

The platform MUST offer exactly one production embedding model. The set of
production model identifiers MUST be a single model family, and the retired
alternative model MUST no longer be selectable, no longer appear as a
production-enabled licence record, and no longer be offered as a deployment
setup option.

#### Scenario: backend swap does not change observable behaviour

Given a test that swaps the default adapter for an alternative
adapter implementing the same port
When the test calls `embed("FinishPack protocol message")` on both
adapters
Then both return a vector of the declared `dimension()`
And both record the same `model_version()` string in the
`VersionIdentity.embeddingModelVersion` field of any chunk they
produced vector for.

#### Scenario: only one production model is offered

Given the production startup profile
When the operator lists the selectable embedding models
Then exactly one production model family is listed
And the retired alternative is absent
