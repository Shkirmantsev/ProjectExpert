# ProjectExpert

**Understand a project without reading every file.** ProjectExpert searches your
project's code and documents so you and your coding assistant can find relevant
information and its sources.

You can ask where a feature is implemented, find a requirement, or investigate
a library your project uses. ProjectExpert works with Java, Python, and
JavaScript/Node.js projects, with [some limits](docs/DEPENDENCY_RESEARCH.md).

**New here?** Follow [Start with Docker](#start-with-docker), then [ask your
first question](#ask-your-first-question). Already installed? See [everyday
commands](#everyday-commands).

## Start with Docker

You need Docker Desktop or Docker Engine with Compose, an internet connection,
GNU Make, and enough disk space for the application and its model. Start Docker first.
Allow time on first startup for Docker to pull the release images and for
ProjectExpert to build the local index.

Open a terminal in the folder of the project **you want to understand**. For
example, if your project is in `~/projects/my-app`, enter:

```bash
cd ~/projects/my-app
```

Replace that path with your own. Run the next two commands in that same folder.

**1. Set up ProjectExpert**

This runs a short-lived container from the OCI registry. It copies the deployment
kit, including the Makefile and Docker Compose files, into
`.project-intelligence-deploy/` inside your project, then exits. You only need
to do this once for that project.

On Linux, the updated exporter assigns the kit to your project-directory owner,
even when the container runs as root. Re-export repairs an existing root-owned
kit while preserving its settings. Use a user-owned project directory.
The updated application also runs cache writers as that user, so
`.project-intelligence-cache/` and new runtime files remain user-owned after
indexing and restarts. This requires the new application image as well as the kit.

```bash
docker run --pull=always --rm -v "$PWD:/deployment" ghcr.io/shkirmantsev/project-intelligence-deployment:dev
```

**2. Start ProjectExpert**

```bash
make -C .project-intelligence-deploy platform-start
```

Make calls the kit's Compose helper, which selects the runtime profile and
starts the ProjectExpert services with Docker Compose. If Make is unavailable,
run `bash .project-intelligence-deploy/start.sh` instead.

Open the address printed after `Service URL:`, usually
**[http://localhost:8765/](http://localhost:8765/)**. Keep Docker running
while you use ProjectExpert. The URL becomes available while indexing is
still underway. Watch **Local index** or check
[/health/ready](http://localhost:8765/health/ready) for search readiness.
Opening the source file `index.html` directly gives a read-only design
preview. Use the service URL for interactive controls.

The `:dev` image is a development version. Setup preserves an existing kit and
its image pins; to update an existing installation, follow the
[upgrade instructions](docs/PRODUCTION_INSTALL.md). If startup fails, see
[troubleshooting](docs/TROUBLESHOOTING.md). See the [installation guide](docs/PRODUCTION_INSTALL.md) for the tested
platform matrix and release status.

<details>
<summary>Using Windows PowerShell?</summary>

Open Windows PowerShell 5.1 or PowerShell 7 in your project folder. With
Docker Desktop running in WSL2 and Linux container mode, use these commands:

```powershell
docker run --pull=always --rm -v "${PWD}:/deployment" ghcr.io/shkirmantsev/project-intelligence-deployment:dev
make -C .project-intelligence-deploy platform-start
```

All kit Make commands use the same syntax in both PowerShell versions. The
kit uses PowerShell 7 when it is on PATH and falls back to Windows PowerShell
5.1. Without GNU Make, run `& .\.project-intelligence-deploy\start.ps1`.
Windows must allow local PowerShell scripts. See the
[deployment kit guide](distribution/deployment/README.md) for its platform
limits and stop instructions.

</details>

## Ask your first question

1. Open the service URL and check **Local index** for readiness.
2. Enter a question, keyword, or code identifier under **Search your project**.
   Select **Search** to see matching excerpts and their source locations.
3. File changes automatically schedule an index update. To refresh on demand,
   select **Update local index**. Compatible parsed data and embeddings are reused.
   During indexing, **Find pages** can still search the saved Wiki.

For example, ask **“Where is order validation implemented?”** Replace “order
validation” with a feature in your project. For the source inventory, open
**Browse the Wiki, sources and graph → List indexed sources**.

| Your goal | Try asking |
|---|---|
| Find where a feature lives | “Where is customer sign-in implemented?” |
| Understand a change | “Which requirements describe the payment flow?” |
| Prepare for a bug fix | “Where is an invalid order rejected?” |
| Investigate a library | Ask a connected coding assistant: “Which version of this library does the project use, and where is it declared?” |

Results depend on the files available and the selected interface and model.
A result can contain retrieved evidence rather than a complete conversational
answer. Check the cited material and ask a more specific question if needed.
For deeper library research and examples, see
[dependency research](docs/DEPENDENCY_RESEARCH.md).

## Browser controls

| Where | When to use it | What to expect |
|---|---|---|
| **Browse the Wiki, sources and graph** | Inspect evidence or navigate from a known entity ID. | **Find pages** searches saved curated Markdown by keyword. **List indexed sources** shows inventory entries, and **Show connections** expands a known entity. |
| **Restore or share via Git** | Reuse a snapshot in the current checkout or share reviewed knowledge. | **Restore from Git** reuses compatible data. If it reports missing work, use **Update local index**. To share manually, enable export and save preferences, then use **Preview Git export → Write reviewed Git files**. Export writes a manifest at `project-knowledge/manifests/portable-v2.json` and its referenced metadata and object files. Commit and push are separate Git actions. |
| **Sharing preferences** | Adjust how you share snapshots. | **Export after index updates** writes eligible data automatically while the one-hour approval is valid. Save the preferences again to renew approval. **Include embeddings** adds eligible vectors for faster restoration. The default generated-file size cap is 8 MiB. |
| **Diagnostics and project version** | Investigate slow or failed indexing, or check which checkout is searchable. | See indexing progress, Git version, and knowledge freshness. Failed files can also be inspected with `platform-index-failures`. |
| **Embedding device and PDF processing** | Change how the local index is built. | **Embedding device** is selectable when the app controls the runtime. For host-managed CUDA/Vulkan, the launcher selects the device. **Include PDFs in the index** enables Docling. **Apply and update index** saves the settings and starts a refresh. |
| **Text encoding overrides** | Correct a file when automatic decoding cannot identify its encoding. Windows-1251 and Windows-1252 are tried automatically. | Add a rule with a project-relative pattern and the original encoding. **Preview decoding** reports counts of matching, decoded, and failed files without saving. **Save rules** stores the rules locally. **Update local index** then applies them. Original files are preserved. |
| **Generated answers** | Request prose answers backed by project excerpts. | Set the provider type, endpoint URL, and exact model ID. Enter a provider key if required. Grant excerpt access for an endpoint you want to receive project context. Save settings, then **Test saved connection**. Use **Generate an answer** next to **Search** to call the provider. |

When `PI_UI_TOKEN` is absent or empty in the running container, anyone who can
reach the UI has administrator access. This applies to local and remote
addresses. A configured token keeps search and browsing available to viewers. The
**Administrator token** form unlocks settings and other privileged actions.
Viewer search can return indexed project content. Run `platform-open` to open
the service URL from the deployment host.
The **Operator workflows** section describes signed approval for canonical writes
and delegation through a connected MCP client.

**Text encoding overrides** work with source files. The older
`PI_OPENAI_BASE_URL` setting belongs to the OpenAI-compatible adapter and is
kept for configuration compatibility. Configure the chat provider in
**Generated answers**. Open WebUI connects to the ProjectExpert service's
`/v1` instead. See [chat frontends](docs/USER_GUIDE.md#open-webui-and-other-chat-frontends).

## Everyday commands

Run these from the same project folder. These commands need GNU Make; the
[kit guide](distribution/deployment/README.md) also describes script-based
alternatives and Windows commands.

| I want to… | Command |
|---|---|
| See available commands and descriptions | `make -C .project-intelligence-deploy` |
| Start again | `make -C .project-intelligence-deploy platform-start` |
| Open the ProjectExpert UI | `make -C .project-intelligence-deploy platform-open` |
| Inspect the active GGUF endpoint | `make -C .project-intelligence-deploy platform-embedding-status` |
| Measure GGUF document throughput on an idle installation | `make -C .project-intelligence-deploy platform-embedding-benchmark` |
| Check whether it is ready | `make -C .project-intelligence-deploy platform-status` |
| See startup messages | `make -C .project-intelligence-deploy platform-logs` |
| Refresh the search index after project changes | `make -C .project-intelligence-deploy platform-reindex` |
| Start and require every source to succeed | `make -C .project-intelligence-deploy platform-start ALLOW_SKIPPED_SOURCES=0` |
| See which files failed | `make -C .project-intelligence-deploy platform-index-failures` |
| Stop ProjectExpert | `make -C .project-intelligence-deploy platform-stop` |

Make startup allows isolated file errors by default. Successfully indexed sources
remain available to local search and MCP. **Local index** and `/api/v1/indexing-status` show
indexed and skipped counts. Model, configuration, and integrity failures still
block publication. Git export requires zero skips. See
[source recovery](docs/PRODUCTION_SOURCE_RECOVERY.md).

Press `Ctrl+C` to leave the live log view. Stopping keeps your downloaded model
cache. Without Make, run `bash .project-intelligence-deploy/compose.sh down` on
Linux or `& .\.project-intelligence-deploy\stop.ps1` on Windows.

## Choose how to use it

| I want to… | Where to go |
|---|---|
| Ask a question in a browser | Open [http://localhost:8765/](http://localhost:8765/) after startup. |
| Give a coding assistant project context | Connect an MCP-compatible assistant to `http://localhost:8765/mcp`. See [MCP setup](docs/USER_GUIDE.md#mcp-for-coding-assistants). |
| Use another chat application | Install it separately and configure the optional Open WebUI compatibility route. See [chat frontends](docs/USER_GUIDE.md#open-webui-and-other-chat-frontends). |
| Connect software or another agent | See the [REST and A2A interfaces](docs/USER_GUIDE.md#choose-an-interface). |

These addresses use the default port. If you change `PI_CONTROL_PORT`, use the
new port instead. Access and authentication settings are explained in the
[user guide](docs/USER_GUIDE.md).

## How it works

```mermaid
flowchart LR
    A[Your project files] --> B[ProjectExpert builds a search index]
    B --> C[You ask a question]
    C --> D[Relevant evidence]
    D --> E[Useful findings can be saved in the Wiki]
    E --> B
```

ProjectExpert reads your project and builds a searchable index. It uses that
index to find evidence for your questions. A coding assistant can save reviewed
findings in the project Wiki; a later refresh makes them searchable. The
[architecture guide](docs/ARCHITECTURE.md) explains the full process and where
the data is stored.

## Configuration

### Do I need to set environment variables?

Short answer: **no.** The deployment kit ships a `deployment.env` file with
working defaults, so `make platform-start` works on a clean installation
without touching your shell at all. You only need environment variables if you
want to override a default for one run.

It helps to keep two things apart:

- **Settings** live in `.project-intelligence-deploy/deployment.env` inside your
  project. It is a plain text file that the kit reads; it is never executed as
  shell code.
- **Environment variables** are optional overrides. A variable exported in your
  shell wins over the file, and the file wins over the built-in default.

### Settings you may want to change

Edit `.project-intelligence-deploy/deployment.env` in your project, or export the
same name in your shell for a single run:

| Setting | Default | What it does |
|---|---|---|
| `PI_TARGET_REPO` | `..` | Which folder gets analysed. The kit sits in `.project-intelligence-deploy/`, so `..` is your project root. Use forward slashes on Windows. |
| `PI_CONTROL_PORT` | `8765` | The port you open in the browser. |
| `PI_BIND_HOST` | `127.0.0.1` | The interface the service listens on. Keep it on loopback unless you really mean to expose it. |
| `PI_EMBEDDING_MODEL` | `gemma` | `gemma` uses the packaged EmbeddingGemma 2 runtime. `gemma-torch` selects the native PyTorch binding. |
| `PI_ACCELERATOR` | `auto` | `auto`, `cpu`, `vulkan` or `cuda`. `auto` picks the fastest backend it can prove works, and falls back to CPU when the GPU is missing, unusable or slower. |
| `PI_GPU_DEVICE` | auto-detected | Pins one device, for example `Vulkan1`. It is honoured only when the runtime actually reports that device. |
| `PI_DOCLING_ENABLED` | `1` | PDF, table and OCR parsing. Set it to `0` to skip that work. |
| `PI_INDEX_REQUIRE_COMPLETE` | `1` for direct launches | Direct scripts and Compose use this setting. Make uses `ALLOW_SKIPPED_SOURCES`, which defaults to `1`. |
| `PI_UI_TOKEN` | unset | Optional bearer passed into the service container. Absent or empty grants administrator access on any bound interface. |
| `PI_IMAGE` | published production image | Pins the application image. Change it only when you upgrade deliberately. |

Stop and start the service after changing the port or the model.

Keep workspace tokens and provider keys out of Git. An operator can supply
`PI_UI_TOKEN` through a private environment. Optional chat credentials are
configured through **Generated answers**.

See the [deployment kit guide](distribution/deployment/README.md) for the full
list of settings, the model and accelerator details, and the upgrade steps.

Working on ProjectExpert itself rather than using it? The repository has its
own `.env` for the development harness; see
[configuration](docs/CONFIGURATION.md).

## No Docker? Use Python

This alternative requires a **ProjectExpert source checkout** and Python 3.11
or newer. The locked requirements below target Python 3.11 on Linux x86_64. Run them in the ProjectExpert
checkout, not in the project you want to analyze:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-production-linux-x86_64.txt -r requirements-production-java-linux-x86_64.txt
.venv/bin/python -m pip install --no-deps '.[production]'
.venv/bin/python -m pip check
```

Then replace `/absolute/path/to/your-project` with the full path to your project:

```bash
.venv/bin/python -m pi_platform.cli start --target /absolute/path/to/your-project --model gemma-torch --device cpu --serve
```

Open [http://localhost:8765/](http://localhost:8765/). This process runs in the
terminal; press `Ctrl+C` to stop it. For other systems and installation limits,
see [install and launch](docs/PRODUCTION_INSTALL.md).

In this mode the settings above are command-line flags (`--target`, `--model`,
`--device`, `--port`), so no environment variables are needed either. The
embedding model is downloaded into your local Hugging Face cache; set
`HF_HOME` if you want it somewhere else.

## More help

- [User guide](docs/USER_GUIDE.md): interfaces, examples, and detailed capability limits.
- [Dependency research](docs/DEPENDENCY_RESEARCH.md): supported languages, library code, and Wiki reuse.
- [Architecture](docs/ARCHITECTURE.md): the components, question flow, and data lifecycle.
- [Troubleshooting](docs/TROUBLESHOOTING.md): startup, readiness, and missing evidence.
- [Documentation map](docs/README.md): all project documentation and contributor guides.
