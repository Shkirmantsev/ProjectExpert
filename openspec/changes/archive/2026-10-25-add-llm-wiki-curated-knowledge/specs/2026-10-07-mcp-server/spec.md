## ADDED Requirements

### Requirement: the MCP server exposes the LLM Wiki surface

The MCP server MUST expose the LLM Wiki tools alongside the canonical
tool names. The tool names MUST NOT shadow the canonical §36 names.

The Wiki tools MUST NOT require the operator approval id. The existing
rule that the write and materialisation tools require it MUST continue to
apply to the derived-knowledge tools.

#### Scenario: the Wiki tools are listed

Given an MCP server
When the client lists the tools
Then the LLM Wiki tools are listed
And the canonical tool names are unchanged

#### Scenario: the Wiki tools do not require an approval id

Given a target repository with an initialised Wiki
When the caller writes a curated page
Then the write succeeds without an approval id
And the derived materialisation tools still refuse a call without an
approval id
