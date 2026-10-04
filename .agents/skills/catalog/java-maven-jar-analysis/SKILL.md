---
name: java-maven-jar-analysis
description: Analyze Maven coordinates, pom.xml dependency trees, and local Java/JAR contents using the project-context MCP jar_search/jar_api hooks, falling back to native javap/jdeps/mvn dependency:* when no backing analyzer is enabled.
---

# Java/Maven/JAR analysis

Use this skill when a task asks about a Java class, a Maven coordinate, a JAR
file's contents, or transitive dependencies in a project that builds with
Maven. Do **not** load it for non-Java dependency questions.

## Boundary

The harness does **not** ship a real Java/JAR analyzer. The MCP hooks are an
**optional contract**; they return a stub until a separate backing analyzer is
enabled in the active project. This skill therefore teaches you how to:

1. recognize whether the hooks are wired up,
2. use them when they are,
3. fall back to native command-line tools when they are not,
4. ask the operator to install the analyzer when neither path is sufficient.

## MCP contract (project-context)

Two optional tools in `tools/mcp/project-context-mcp/project_context_mcp/server.py:67-75`
expose a hook for Java/Maven introspection:

- `jar_search(query)` — search for classes, artifacts, or Maven coordinates.
- `jar_api(gav, class_name)` — request class-level data for a specific Maven
  coordinate (`groupId:artifactId:version`) and class FQN.

Stub response (current behavior, **before** any future analyzer is added):

```json
{"query": "...", "available": false,
 "message": "Install/enable a Java/JAR analyzer skill for deterministic Maven/JDK dependency inspection."}
```

When the agent receives `available: false`, **stop calling the hook** for this
session; treat it as absent. See `.ai/wiki/interfaces/java-jar-analyzer.md` for
the contract details.

## Decision rules

Follow these in order:

1. **Identify the target.** Accept either a Maven project (`pom.xml`, `mvnw`,
   or `.mvn/`) or an explicit local `.jar` / `.class` path. If neither is
   available, ask for the artifact path or Maven coordinate instead of
   guessing. A Gradle-, Bazel-, sbt-, or Ant-only project belongs elsewhere.
2. **Check whether the analyzer is enabled.** If `jar_search` is available in
   the active MCP toolset, call it with a small probe query. If `available` is
   `true`, use the hooks for subsequent questions. If the tool itself is not
   available, proceed directly to the native fallback.
3. **Fall back when the hook is stubbed.** Use one of:
   - `javap -classpath <jar> -p -c <class>` for class structure (works against
     local class files or JARs; no network).
   - `jdeps -v -R <jar>` for transitive package dependencies (JDK 8+).
   - `mvn dependency:tree` for the full Maven dependency graph
     (offline mode preferred: `mvn -o dependency:tree`).
4. **Escalate when the answer is unknown.** Ask the operator to install a
   backing Java/JAR analyzer implementation, or to provide the artifact path.
   Do **not** download JARs from Maven Central without explicit approval.

## What this skill does NOT do

- It does not grant new MCP tools. Tool authority is unchanged.
- It does not modify `project-context-mcp/server.py`. The stub remains.
- It does not run Maven outside a confirmed Maven target.
- It does not cover Gradle, Bazel, sbt, or non-Maven build systems.

## Related knowledge

- `.ai/wiki/interfaces/java-jar-analyzer.md` — full hook contract and stub
  response shape.
- `.ai/wiki/modules/java-maven-jar-analysis.md` — ownership, routing
  triggers, and links to this skill.
- `openspec/changes/java-maven-jar-skill-adoption/` — the change that
  adopted this skill.
- `.ai/wiki/architecture/system-overview.md` — MCP ownership boundary.

## Evidence to capture when answering

When you answer a Java/Maven question, record:

- the source (MCP hook, `javap`, `jdeps`, or `mvn dependency:tree`),
- the exact command or tool call,
- the file paths or coordinates you resolved,
- any operator approval obtained for network access.

This evidence is what verification will check, not the prose answer.
