## MODIFIED Requirements

### Requirement: EmbeddingProfile descriptor

The platform MUST define `EmbeddingProfile` with the
following fields: `provider`, `model_id`,
`model_revision`, `modality`, `output_dimension`,
`normalization`, `instruction_profile`, `tokenizer_id`,
`strategy_version`.

The identity key is
`sha256(canonical(EmbeddingProfile))`. The canonical
serialisation MUST use sorted keys, no volatile data
(timestamps, hostnames, paths), and a documented JSON
shape.

The profile identity MUST cover the model fingerprint, which includes the
artefact repository, the artefact revision, the artefact checksums, the
quantisation, the pooling type, the normalisation and the output dimensions.
A change to the projector, to the quantisation or to the pinned revision MUST
therefore produce a different identity and MUST NOT be mixed with vectors
produced under the previous identity.

The execution backend MUST NOT participate in the identity: switching
between CPU and GPU execution of the same pinned artefacts MUST NOT require a
reindex when the outputs remain within the accepted parity tolerance.

#### Scenario: same profile produces the same identity

Given two `EmbeddingProfile` instances with identical
fields in different insertion order
When the platform computes the identity key
Then the two identity keys are byte-identical.

#### Scenario: a changed projector changes the identity

Given a profile pinned to one projector checksum
When the pinned projector checksum changes
Then the identity key changes
And the previous vector space is not opened with the new identity
