# jar-dependency-intelligence Specification delta

Covers architecture section §15 (JAR and Dependency Intelligence) plus
the Maven and Gradle dependency-graph extraction described in §14.
Produces the artifact-coordinate entities, signature / inheritance /
module entities and dependency relations that the Phase 3 graph and
the Phase 4 retrieval depend on.

The Phase 1 `canonical-knowledge-schema`, `git-version-aware-runtime`
and `license-governance` capabilities provide the entity/relation
value types, the SHA-256 content address and the SPDX-tracked
dependency gate that this spec builds on.

## ADDED Requirements

### Requirement: JarAdapter

The platform MUST expose a `JarAdapter` that implements the
`SourceAdapter` port (see `document-source-adapters`) and produces
the following entities per JAR:

- one `Dependency` entity per JAR with attributes
  `groupId`, `artifactId`, `version`, `classifier`, `type`
  (`jar` | `sources` | `javadoc` | `war` | `ear`);
- one `JavaPackage` entity per declared package inside the JAR;
- one `JavaClass` entity per public class with attributes
  `packageName`, `className`, `modifiers`;
- one `JavaInterface` entity per public interface;
- one `JavaMethod` entity per public method signature (the JAR does
  not contain bodies);
- one `Annotation` entity per runtime-visible annotation;
- one `InheritedType` relation per `extends`/`implements` link to a
  class or interface outside the JAR;
- one `Module` entity for `module-info.class` when the JAR is a Java
  module;
- one `Resource` entity per non-class resource path;
- one `PublicApi` entity per exported package or module declaration;
- `DEPENDSON`, `DECLARED_BY`, `DOCUMENTED_BY`, `CONTAINS` relations
  per the architecture §16 catalogue.

The `JarAdapter` MUST read each JAR through the same content-addressed
processing contract documented in `content-addressed-processing`: the
JAR's SHA-256 hex digest of its deterministic byte stream is the
adapter's primary cache key so identical JAR bytes produce a single
set of canonical entities across branches.

#### Scenario: JarAdapter emits dependency entities

Given a JAR file at `lib/example-1.2.3.jar` whose `MANIFEST.MF`
declares `Implementation-Title: example`,
`Implementation-Version: 1.2.3` and whose `META-INF/MANIFEST.MF`
lists no `Premain-Class`
When the `JarAdapter` is invoked on the file
Then the adapter emits one `Dependency` entity with
`groupId="com.example"`, `artifactId="example"`, `version="1.2.3"`
And the adapter emits one `JavaPackage` entity per package declared
by the JAR
And the adapter emits one `JavaClass` entity per public class with
attributes `packageName` and `className`
And every emitted entity carries an `Evidence` record with
`parserVersion` matching the documented parser adapter version.

#### Scenario: source-JAR content is preferred

Given a JAR `lib/example-1.2.3.jar` and a source JAR
`lib/example-1.2.3-sources.jar` located at the documented relative
path
When the `JarAdapter` is invoked
Then the adapter prefers the source-JAR for class signatures when
the source JAR is present
And the adapter records the source JAR's SHA-256 hex digest as the
`sourceHash` of the resulting `JavaClass` entities
And the operational log names both JAR paths.

### Requirement: MavenAdapter

The platform MUST expose a `MavenAdapter` that implements the
`SourceAdapter` port and produces a `Dependency` entity per
`<dependency>` in a target `pom.xml`, plus `DEPENDSON` relations per
the resolved dependency tree (resolved against `mvn dependency:tree`
output when the Maven CLI is available, or against a documented
deterministic parser fallback when it is not).

#### Scenario: MavenAdapter parses pom dependencies

Given a `pom.xml` declaring three `<dependency>` entries
`com.a:b:1.0.0`, `com.a:c:1.1.0` and `com.b:d:2.0.0`
When the `MavenAdapter` is invoked
Then the adapter emits three `Dependency` entities with the
documented `groupId`, `artifactId` and `version` triples
And the adapter emits one `PART_OF` relation per dependency linking
the dependency to the enclosing `MavenModule` entity
And the adapter persists the dependency through the Phase 1 license
gate's SPDX inventory when `groupId` matches a known coordinate.

### Requirement: GradleAdapter

The platform MUST expose a `GradleAdapter` that implements the
`SourceAdapter` port and produces a `Dependency` entity per declared
Gradle module dependency. The adapter MUST support Gradle Groovy DSL
(`build.gradle`) and Gradle Kotlin DSL (`build.gradle.kts`) and MUST
record the parser version used for each build script.

#### Scenario: GradleAdapter parses build.gradle.kts

Given a `build.gradle.kts` declaring `implementation("com.a:b:1.0.0")`
and `testImplementation("com.c:d:2.0.0")`
When the `GradleAdapter` is invoked
Then the adapter emits two `Dependency` entities
And the dependency carrying the test configuration is tagged with
`scope="test"`.

### Requirement: dependency-graph extraction

The `MavenAdapter` and `GradleAdapter` MUST expose a `resolve_tree`
operation that, given a project root and a build-tool binary, returns
the resolved dependency tree as `DEPENDSON` relations. When the build
tool is absent the adapter MUST return the declared dependencies
only and record a `transient` advisory so the operator knows the tree
is partial.

#### Scenario: absent Maven CLI yields partial tree

Given a project root whose `pom.xml` declares 3 dependencies and a
PATH that does not contain `mvn`
When the `MavenAdapter.resolve_tree(...)` is called
Then the returned tree contains the 3 declared `DEPENDSON` relations
And the adapter records an operational log entry naming the missing
`mvn` binary and the dependency count that is unverified.

### Requirement: license pass-through

Every Dependency entity emitted by JarAdapter, MavenAdapter and GradleAdapter MUST carry the SPDX identifier of the dependency when one is available in distribution/licenses/dependency-inventory.json.

#### Scenario: dependency without SPDX is surfaced as assumption

Given a `Dependency` entity `com.x:y:1.0.0` whose SPDX identifier is
not present in `distribution/licenses/dependency-inventory.json`
When the adapter emits the entity
Then the entity's `Evidence.knowledgeState` is `ASSUMPTION`
And the entity's metadata contains `sourcePath` pointing at the JAR
or build file
And the Phase 1 license gate surfaces the dependency on the next
build with `decision="review"`.

## Phase 2 task coverage

The change lists Phase 2 tasks 52 (`JarAdapter`), 53
(`MavenAdapter` + `GradleAdapter`) and the
`jar-dependency-intelligence` slice of task 58 (Phase 2 spec
scenarios) and task 59 (focused regression tests per adapter).

Out of scope:

- bytecode-level decompilation into source code (the JAR adapter
  exposes signatures and structure, not decompiled bodies);
- the runtime DB schema for the dependency entities (Phase 3 task
  62);
- the MCP tools `project.get_dependency` and `project.find_references`
  that consume the dependency graph (Phase 6 task 85).