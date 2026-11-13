## ADDED Requirements

### Requirement: BM25 ties preserve upstream relevance
BM25-light MUST retain the deterministic incoming semantic/fusion order when
lexical scores are equal, including all-zero overlap. Candidate identifiers MUST
NOT substitute for relevance when the lexical reranker has no distinguishing
evidence. Non-tied lexical scores and rerank score/rank propagation remain effective.

#### Scenario: translated query has no lexical overlap
- **GIVEN** a semantically ranked candidate set and a query in another language
- **WHEN** BM25-light finds no matching lexical terms
- **THEN** the candidate order remains the incoming semantic/fusion order
- **AND** the selection stage retains that ordering

#### Scenario: equal nonzero lexical scores
- **WHEN** two candidates have equal positive BM25-light scores
- **THEN** their incoming relative order is preserved
