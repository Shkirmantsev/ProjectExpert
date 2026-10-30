# Container search, local documents and the trade-analyzer upgrade

Search uses EmbeddingGemma 2 embeddings, lexical retrieval, fusion and optional
BM25-light reranking. It needs embedding inference, not a generative chat LLM.
The browser and Open WebUI both use the same published retrieval generation.

## What was observed on 2026-10-30

The trade-analyzer deployment published production on host port 8766 and Open
WebUI on 8768, on Docker network `project-intelligence_default`. The embedding
sidecar had no published host port. Read-only checks found a ready Gemma/USearch
index with 345 sources and 3,470 active chunks; both query and retrieve returned
HTTP 200. Earlier refreshes failed because project files changed during indexing,
then retried successfully. One Python file (`backtest_v4_modified.py`, line 29)
failed parsing due to an invalid f-string; other sources remained searchable.
These observations describe that deployment at check time, not a universal gate.

The UI had separate bugs: obsolete model options, no job polling, misleading
chat settings, source projection disconnected from the published inventory,
raw JSON Wiki output, and generic readiness errors. Automatic discovery omitted
the accepted local inbox. Open WebUI streaming requests were rejected. The repair
addresses those paths and preserves the readiness boundary during refresh.

## Upgrade the application used by trade-analyzer

Changes in a ProjectExpert checkout do not update an already running container.
This work does not publish an image or edit the trade-analyzer repository.
Build the repaired production application from this checkout:

```bash
cd /home/dmytro/workspace/personal_projects/ProjectExpert/ProjectExpert
docker build -f Containerfile --target production -t project-intelligence:search-ui-fix .
```

In
`/home/dmytro/workspace/personal_projects/trade-analyzer/trade-analyzer/.project-intelligence-deploy/deployment.env`,
set `PI_IMAGE=project-intelligence:search-ui-fix`. Preserve all other values,
especially the target, control port 8766, accelerator selection and existing
Open WebUI configuration. If an exported kit has literal digest pins instead
of `${PI_IMAGE}` substitution, inspect its Compose image fields and replace only
the production and model-setup application image pins with this local tag.
Keep the pinned embedding runtime image and model files.

Then use the existing launcher's complete topology:

```bash
cd /home/dmytro/workspace/personal_projects/trade-analyzer/trade-analyzer/.project-intelligence-deploy
make platform-start
```

`up` recreates application containers whose image/config changed. A plain
`restart` keeps the old image. Do not delete model volumes or the runtime cache.
The new application reuses matching vectors and adds inbox sources. Hard-refresh
the browser to load the new static assets. Use **Trigger reindex** in the UI to
run a job in the serving process and watch its completion/failure.

Check:

```bash
curl -f http://127.0.0.1:8766/health/ready
curl -f http://127.0.0.1:8766/api/v1/sources
curl -f http://127.0.0.1:8766/api/v1/indexing-status
```

Use the API bearer token if your operator configured authentication; do not copy
credentials into documentation or command history. While indexing, HTTP 503 is
expected: the status panel shows progress and the actual failure reason. Wait for
readiness. Persistent errors require `make platform-logs`, not a chat LLM install.

## Private source documents

Use `tmp/` in the **target project**, including arbitrary document subfolders.
The existing `tmp/local/source/` inbox remains supported:

```text
/home/dmytro/workspace/personal_projects/trade-analyzer/trade-analyzer/
  tmp/local/source/
    reports/portfolio.pdf
    requirements/customer-notes.md
```

The repaired automatic indexer includes this inbox and supported untracked files
under `tmp/` (for example `tmp/reports/portfolio.pdf`), monitors edits/deletions,
uses the 256 MiB default per-file limit, and preserves `LOCAL_ONLY` metadata.
Hydration adds `/tmp/` and the configured inbox to the target's `.git/info/exclude`; verify before
adding files with `git check-ignore tmp/local/source/reports/portfolio.pdf`.
The rest of `tmp/local/`, deployment files and runtime caches stay excluded from
search. Supported Markdown/text/HTML/PDF and source formats use their existing
adapters. PDF processing requires the Docling toggle and provisioned model/OCR
assets; an initial PDF may need asset downloads and additional indexing time.
Do not assume arbitrary office formats are supported.

The inbox can be configured in `project-knowledge/project-context.yaml`:

```yaml
sources:
  localInbox:
    path: tmp/local/source
    maxSourceBytes: 268435456
    policies:
      '**': LOCAL_ONLY
```

The path must remain inside the target repository without symlink escapes.
Git-tracked inbox sources are skipped by the inbox scanner. Raw documents,
extracted chunks and vectors remain local. They do not automatically become
reviewed Wiki articles: embedding inference cannot perform that synthesis.
Ask your MCP-connected agent to retrieve the documents and propose/curate pages
under `project-knowledge/wiki/`. Review confidential source content before
promoting it into tracked Wiki files. LOCAL_ONLY is an ingestion promotion policy,
not a promise that arbitrary agent-authored prose can never reproduce a source.

## UI and Open WebUI

- **Search project evidence** returns ranked excerpts and source paths; it does
  not invent an answer. **Run deterministic retrieval** searches the same text
  and also provides context evidence through the API.
- **Initialise** saves device/PDF settings, requests a serving-process refresh and
  waits for readiness. **Trigger reindex** polls its job until completed or failed.
  Both actions disable duplicate clicks and show a busy indicator.
- **List sources** describes the published inventory, including parser failures.
- **Browse the Wiki** searches curated Markdown; template index/log pages are
  expected until an agent writes useful articles. Results show readable page text.
- **Materialise approved knowledge** is an advanced canonical write operation.
  Search does not need it. No token issuance workflow is provided by this UI.
  `PI_APPROVAL_KEY` is a signing secret; the approval is a separately issued,
  scoped, signed token and still needs administrator policy. The UI hides this
  unusable form instead of asking normal search users for an arbitrary token.
- **Delegate a complex task** is unavailable in retrieval-only orchestration.
  Use Claude Code/Codex/another MCP client with its own model. The UI hides the
  form and the API cannot falsely report a retrieval result as delegated work.
- **Optional chat LLM** provides a working server-side connection: choose the API
  type, base URL, exact chat model and credentials, authorize context sharing,
  then Save and Test. It enhances Ask and Open WebUI answers. Deterministic
  retrieval remains independent. See [configuration and active-mode guide](OPTIONAL_CHAT_AND_EXECUTION_MODE.md).
- **Active mode** shows the effective embedding CPU/GPU/Hybrid mode and its
  evidence source separately from requested Auto. Unknown means no reliable
  runtime evidence is available.

For the observed Docker topology, configure an OpenAI connection in Open WebUI:

```text
Connection URL: http://production:8765/v1
Model:          project-intelligence
```

`production` is Docker DNS for the application service on the shared network;
8765 is its container port. Host port 8766 is for host applications/browser access.
The repair accepts both JSON completions and finite SSE responses. Clients display
cited retrieval evidence without a chat LLM, or a grounded generated answer when
the optional saved chat connection is enabled. SSE framing here
is independent of the MCP Streamable HTTP transport. Existing persistent Open
WebUI connection settings must be updated by its operator if they still point to
a missing local-llm service. No Open WebUI account/settings were modified here.

A separate direct Open WebUI-to-LM Studio chat connection typically uses its reachable server URL
(such as `http://host.docker.internal:1234/v1`, with host networking/reachability
configured). It has no automatic ProjectExpert context. To combine an LLM with
project tools, use an agent/MCP integration; merely entering an LLM URL cannot
supply that integration.
