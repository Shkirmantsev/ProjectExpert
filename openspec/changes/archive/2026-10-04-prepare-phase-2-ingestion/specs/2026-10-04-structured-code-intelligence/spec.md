# structured-code-intelligence Specification delta

Covers architecture section §14 (Structured Code Intelligence) for the
Java source corpus. The capability extracts the structural entities
(Maven modules, packages, classes, interfaces, methods, constructors,
inheritance, annotations, calls, JPA mappings, configuration, tests)
that the Phase 3 graph and Phase 4 retrieval depend on.

The Phase 1 `canonical-knowledge-schema`, `git-version-aware-runtime`
and `license-governance` capabilities provide the entity/relation
value types, the SHA-256 content address and the SPDX-tracked
dependency gate that this spec builds on.

## ADDED Requirements

### Requirement: Java structured adapter

The platform MUST provide a `JavaStructuredAdapter` that implements the
`SourceAdapter` port (see `document-source-adapters`) and produces:

- one `MavenModule` entity per `<module>` element in `pom.xml`;
- one `JavaPackage` entity per declared Java package;
- one `JavaClass` entity per top-level and nested class declaration;
- one `JavaInterface` entity per `interface` declaration;
- one `JavaMethod` entity per method or constructor declaration;
- one `Annotation` entity per annotation usage;
- one `JPAEntity` entity per `@Entity`-annotated class with the
  declared table name, schema and column mappings;
- one `Test` entity per JUnit `@Test`-annotated method per test class;
- `IMPLEMENTS`, `EXTENDS`, `CALLS`, `ANNOTATED_BY`, `MAPPED_BY`,
  `TESTED_BY` relations per the architecture §16 catalogue;
- an `Evidence` record per entity/relation whose
  `KnowledgeState.VERIFIED` is set when the source file parses and
  whose `parserVersion` matches the documented parser adapter
  version.

The adapter MUST operate against the documented Java parser library
recorded in `adr.phase-2-parser-selection` (the design candidate is
`tree-sitter-java` MIT invoked as an out-of-process
subprocess) and MUST pass every SPDX-tracked dependency through `LicenseGate`
before the adapter is registered.

#### Scenario: JavaAdapter emits class entities

Given a source file `src/main/java/com/example/Foo.java` containing
one top-level class `Foo` with two methods `bar()` and `baz()` and
the class extends `BaseFoo` and implements `Iface`
When the `JavaStructuredAdapter` is invoked on the file
Then the adapter emits one `JavaClass` entity labelled `Foo` with
metadata `language="java"`, `className="com.example.Foo"`
And the adapter emits two `JavaMethod` entities labelled `bar` and
`baz` linked to `Foo` by `PART_OF`
And the adapter emits a `BaseFoo` `JavaClass` entity linked by
`EXTENDS`
And the adapter emits an `Iface` `JavaInterface` entity linked by
`IMPLEMENTS`
And every entity carries `Evidence` with
`KnowledgeState.VERIFIED` and the parser adapter's `parserVersion`.

#### Scenario: missing parser binary fails closed

Given a configured `JavaStructuredAdapter` whose parser executable is
not present on `PATH` and `project-context.yaml` sets
`javaParser.required=true`
When the adapter is invoked
Then the adapter raises a `configuration_error` with a clear message
And the driver refuses to continue with the next source
(no source is processed while the Java parser is required but
missing).

### Requirement: Java parser library license contract

The platform MUST expose a `JavaParserPort` in
`pi_platform/ports/ingest/java_parser.py` whose default adapter lives
in `pi_platform/adapters/java/parser_subprocess.py`. The adapter MUST:

- invoke the parser binary as an out-of-process subprocess and parse
  its JSON output through the standard library;
- record the parser binary path, version and SPDX identifier in
  `distribution/licenses/dependency-inventory.json` so the
  `LicenseGate` can validate the dependency on every build;
- refuse to register the adapter when the parser binary's SPDX
  identifier is missing, not in the allow list, or marked
  `review-required` without an acceptance entry in the inventory;
- document the parser lifecycle ownership so a future operator can
  swap the default library (`tree-sitter-java` MIT) for an
  alternative (`javalang` MIT, `javaparser` Apache-2.0, native
  `javap`/`jdeps` shell-out) by replacing the adapter only.

#### Scenario: LicenseGate rejects undeclared parser license

Given a `JavaParserPort` registered against a parser binary whose
SPDX identifier is missing from
`distribution/licenses/dependency-inventory.json`
When `LicenseGate.run(...)` is executed as part of CI
Then `LicenseGate` returns `(False, [finding])` with `decision="deny"`
And the build fails before the adapter is activated
And the operational log records the missing SPDX identifier.

#### Scenario: subprocess timeout is bounded

Given a parser subprocess that does not exit within the documented
stage timeout (default 60 s)
When the adapter invokes the subprocess
Then the adapter terminates the process
And the adapter raises a `transient` error
And the driver retries per the `ingestion-pipeline-driver` error
handling contract.

### Requirement: JPA mapping and configuration extraction

The `JavaStructuredAdapter` MUST extract:

- `@Entity`, `@Table`, `@Column`, `@JoinColumn`, `@OneToMany`,
  `@ManyToOne`, `@ManyToMany`, `@OneToOne` annotations into
  `JPAEntity` entities and `MAPPED_BY` relations;
- `application.yml` / `application.properties` keys into
  `ConfigurationProperty` entities (best-effort, typed by inference).

#### Scenario: JPA mapping extracted

Given a class `Order` annotated with `@Entity`, `@Table(name="orders")`
and a `List<OrderLine>` annotated with `@OneToMany(mappedBy="order")`
When the adapter parses the source file
Then the adapter emits a `JPAEntity` entity for `Order` with
`tableName="orders"`
And the adapter emits a `MAPPED_BY` relation from the `order` field
to `OrderLine`.

### Requirement: test extraction

The `JavaStructuredAdapter` MUST extract every JUnit 5 (`org.junit.jupiter
.api.Test`) and JUnit 4 (`org.junit.Test`) annotated method as a `Test`
entity and link it to its enclosing class by `TESTED_BY` plus a
`PART_OF` from the class to the test class.

#### Scenario: test methods extracted

Given a class `OrderServiceTest` containing two `@Test`-annotated
methods `createsOrder` and `failsOnNegativeAmount`
When the adapter parses the source file
Then the adapter emits two `Test` entities
And each `Test` entity is linked by `PART_OF` to `OrderServiceTest`
And each `Test` entity is linked by `TESTED_BY` to `OrderService`
when the test method's body references the production class.

## Phase 2 task coverage

The change lists Phase 2 task 51 (`JavaStructuredAdapter`) and the
`structured-code-intelligence` slice of task 58 (Phase 2 spec
scenarios) and task 59 (focused regression tests per adapter).

Out of scope:

- non-Java languages (Kotlin, Scala, TypeScript) — separate Phase 2+
  adapters;
- the embedded DB schema that stores the entities (Phase 3 task 62);
- the dense ANN index over the source code embeddings (Phase 4 task
  71).