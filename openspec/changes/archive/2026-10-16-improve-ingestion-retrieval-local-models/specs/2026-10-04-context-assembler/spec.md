# 2026-10-04-context-assembler Specification delta

Covers plan §6, §5.3.

## ADDED Requirements

### Requirement: PRIMARY / PROTECTED / SUPPORT / RESERVE awareness

The `ContextAssemblerPort.assemble` operation MUST
consume candidates whose `SelectionState` is one of
`PRIMARY | PROTECTED | SUPPORT | RESERVE` and MUST
assemble them in the following order, stopping at the
configured `contextBudget`:

1. protected direct evidence;
2. authoritative `PRIMARY` evidence;
3. other `PRIMARY` evidence;
4. mandatory `SUPPORT` nodes;
5. conflict-support evidence;
6. reserve escalation for uncovered subtopics;
7. optional additional `SUPPORT`.

The assembler MUST collapse near-duplicates by
normalised content hash / similarity while
preserving links to the collapsed equivalents;
duplicate provenance MUST NOT be discarded.

#### Scenario: protected evidence is included before support

Given a context budget of 1024 tokens and candidates
with mixed `SelectionState`
When the platform calls
`ContextAssemblerPort.assemble(...)`
Then protected direct evidence appears in the
returned `ContextBundle` before any `SUPPORT` node
And `RESERVE` candidates are only added if the
budget is not exhausted.

#### Scenario: duplicate provenance is preserved

Given three near-duplicate candidates
When the assembler collapses them
Then the surviving candidate carries a link to the
collapsed equivalents
And the dropped duplicates are recorded under
`droppedHits` with reason `deduplicated` and their
provenance is preserved in the trace.

### Requirement: reserve escalation

The assembler MUST escalate from the `RESERVE` pool
when any of the following holds: the primary chunks
are near-duplicates; the answer has multiple
subquestions; a needed source type is absent;
conflict verification requires more evidence; the
budget is not exhausted; or an answer verifier
requests more evidence.

#### Scenario: reserve escalates for multi-subquestion answer

Given a primary set of 8 candidates that cover only
one of three subquestions
When the assembler runs
Then it pulls `RESERVE` candidates until all three
subquestions have at least one evidence link or
the context budget is exhausted.

## MODIFIED Requirements

None. The existing context-assembler
`Requirements` (assembler contract, deduplication)
are preserved. The new selection-awareness and
reserve escalation are additive.
