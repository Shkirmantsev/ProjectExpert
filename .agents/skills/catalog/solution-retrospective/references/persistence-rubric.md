# Persistence rubric

## Update repo AGENTS.md when

- The lesson depends on this repo's structure, build/test commands, conventions, boundaries, or architecture.
- The next agent could avoid wasted reading, editing, or verification by seeing one short rule first.
- The rule can be phrased concretely.

Examples:

- "In this module, run `./mvnw -pl service-a -am test` before editing adjacent modules."
- "For database changes, update Liquibase changelog before repository code."
- "Do not modify generated DTOs; change the generator input under `schema/`."

## Update an existing project skill when

- The lesson is a repeatable workflow pattern.
- It applies across more than one repository.
- There is already a related project skill whose scope can be improved without becoming vague.

Examples:

- A better bugfix triage sequence.
- A better commit grouping routine.
- A better method for verifying schema-impacting changes.

## Create a new project skill only when

All are true:

- The pattern is concrete.
- It is likely to recur.
- It saves meaningful time or avoids recurring waste.
- No existing project skill already covers it.
- The skill can be kept short and specific.

## Do nothing when

- The issue was a one-time typo.
- The root cause was a transient outage or credentials problem.
- Existing tests/linters already prevent recurrence.
- The evidence is too weak to justify new instructions.
