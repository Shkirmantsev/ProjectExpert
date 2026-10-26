## MODIFIED Requirements

### Requirement: text and image loading

The platform MUST load the pinned EmbeddingGemma 2 checkpoint in the
quantisation that the production deployment pins, and MUST load the
matching multimodal projector so that image, audio and video inputs are
available through the production binding.

The projector MUST be part of the pinned artefacts: the backbone and the
projector MUST be pinned by revision and verified by checksum, and both MUST
be present for the multimodal profile to be advertised.

The platform MUST discover which modalities the loaded runtime actually
supports and MUST NOT advertise a modality that the runtime does not
support.

#### Scenario: the multimodal package is loaded by default (verifies: text and image loading)

Given the production deployment with an empty model cache
When the setup step completes
Then the pinned quantised backbone is present and verified
And the pinned multimodal projector is present and verified
And the runtime reports the multimodal capability

#### Scenario: a missing projector is reported, not assumed (verifies: text and image loading)

Given a model cache that contains the backbone but not the projector
When the runtime starts
Then the platform reports which modalities are unavailable
And the platform does not advertise image, audio or video embedding
And the text-only capability remains usable

#### Scenario: an unsupported modality is refused (verifies: text and image loading)

Given a runtime that does not advertise audio input
When a caller requests an audio embedding
Then the request is refused with an explicit unsupported-modality error
And no substitute vector is returned

#### Scenario: image pixels participate in embeddings

Given the production profile selects Gemma with its vision components loaded
When two different supported images are embedded
Then their pixel content is passed to the model
And the outputs are normalized 512-dimensional vectors
And changing image bytes invalidates the cached image embedding.
