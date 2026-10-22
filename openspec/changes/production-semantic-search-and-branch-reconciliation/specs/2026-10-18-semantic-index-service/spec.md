# semantic-index-service Specification delta

Covers plan §24–§26 (PR 5 of §79).

## Purpose

Define the persistent semantic indexing behaviour: stored vectors are
the authoritative embedding storage, each embedding profile owns
exactly one vector namespace, only missing vectors are computed,
unchanged retrieval text always reuses its stored vector, and switching
the embedding model reuses existing source and chunk knowledge while
building or reusing the selected profile's namespace and leaving
canonical Git knowledge untouched.

## ADDED Requirements

### Requirement: stored vectors are authoritative

The platform MUST treat persisted vector records as the authoritative
embedding storage for the runtime. Rebuilding a search index MUST reuse
stored vectors and MUST NOT re-run the embedding model for content whose
retrieval text and profile identity are unchanged.

#### Scenario: deleting the index does not require re-embedding (verifies: stored vectors are authoritative)

Given a populated vector store and an existing index namespace
When the index namespace is deleted and rebuilt
Then the rebuild completes using stored vectors
And the embedding model is not invoked

### Requirement: embed only misses

When refreshing the semantic index, the platform MUST look up an
existing stored vector for every chunk before embedding and MUST embed
and persist only the chunks with no matching stored vector.

#### Scenario: unchanged text is not re-embedded (verifies: embed only misses)

Given a namespace with stored vectors for the active profile
And one chunk whose retrieval text changed since the last run
When the platform refreshes the semantic index
Then only the changed chunk is embedded
And the unchanged chunks reuse their stored vectors

### Requirement: one namespace per profile identity

The platform MUST keep every vector in a namespace identified by the
embedding profile identity. The platform MUST reject any operation that
would insert or compare vectors from a different profile identity into
that namespace, and the rejection error MUST NOT leak content beyond the
identities involved.

#### Scenario: cross-profile insert is rejected (verifies: one namespace per profile identity)

Given a namespace belonging to profile identity A
When an operation attempts to insert a vector produced under profile identity B
Then the operation is rejected with a redacted error
And the namespace content is unchanged

### Requirement: reuse key

The platform MUST key vector reuse on the retrieval-text content hash
together with the profile identity, so that a text change or a profile
change both force a new vector while unrelated changes do not.

#### Scenario: text change forces a new vector (verifies: reuse key)

Given a chunk whose stored vector was produced from retrieval text T1
When the chunk's retrieval text becomes T2 and the profile is unchanged
Then the platform embeds T2 and stores a new vector
And the T1 vector is no longer used for that chunk

### Requirement: model switch reuses source knowledge

When the operator switches the embedding model, the platform MUST reuse
existing parsed source and chunk knowledge, MUST compute only the new
profile's missing vectors, MUST build or reuse the selected profile's
index namespace, and MUST NOT modify canonical project knowledge.

#### Scenario: model switch leaves canonical knowledge untouched (verifies: model switch reuses source knowledge)

Given an indexed project running with the Gemma profile
When the operator switches to the Qwen profile
Then existing source and chunk knowledge is reused
And only missing Qwen-profile vectors are computed
And canonical project knowledge files are byte-identical before and after

### Requirement: count validation

After building or loading a namespace, the platform MUST validate that
the indexed vector count matches the expected active chunk count for the
profile and MUST fail activation on mismatch instead of serving an
incomplete index.

#### Scenario: count mismatch blocks activation (verifies: count validation)

Given a built namespace whose indexed count differs from the active chunk count
When the platform validates the namespace
Then activation fails with a clear error
And the previous active namespace remains active
