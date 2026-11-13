# Context impact

Update durable Wiki explanation for production indexing and operator guide.
Retain current specs and CURRENT because target-platform release gates remain
unverified; this active change records implemented opt-in behavior and outstanding
release requirements. Add an ADR documenting atomic source state and separate
candidate artifacts. Generated evidence and temporary benchmarks stay local.

PR24 follow-up updates the release-gate and retrieval-candidate-selection Wiki
nodes. A reranker delta records stable semantic/fusion ordering on lexical ties.
The historical hashing comparator is test-only and explicit; its pre_change JSON
is preserved, while default benchmarks and real-model gates use current ranking.
