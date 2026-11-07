# Portable deployment repair and trade-analyzer upgrade

This repair was developed against the installation report for upstream
`43baa9a67ec2a5a16ce30b77a5f78a293998ed09`. It does not publish new GHCR artifacts
or change the trade-analyzer working tree. Its existing staged changes must be
reviewed separately. Do not describe a local source fix as already deployed.

## Confirmed causes and changes

The managed sidecar had context 2048, batch 1024 and microbatch 1024. A
1049-token input can exceed the noncausal embedding batch limit despite fitting
the context. All three shipped limits now default to 4096 with one parallel
slot, consistently for CPU, CUDA, Vulkan and native launch plans. This provides
headroom for the reported input; it does not promise support for unbounded
inputs. The real-model release smoke now uses these same defaults and exercises
a document whose runtime tokenization exceeds 1049 tokens.

The exported kit now includes an optional `open-webui` profile, pinned to the
existing approved 0.6.5 version. It uses the internal address
`http://production:8765/v1`, independent of host port 8766. The probe uses Python
and checks `/health` JSON status; it bypasses the image's curl/jq probe. The
[pinned upstream Dockerfile](https://github.com/open-webui/open-webui/blob/v0.6.5/Dockerfile)
contains that original healthcheck. Open WebUI calls the ProjectExpert adapter,
which returns retrieved project evidence without a chat model and optionally
adds a generated answer through the shared ProjectExpert chat settings.

A regression injects an embedding failure, retries against the same cache and
confirms readiness becomes true, the failure reason clears and chat settings
survive. A permanently sticky first-error condition was **not reproduced**.
Routine recovery must not delete `.project-intelligence-cache`: it contains
saved provider settings/credentials as well as reusable vectors. `hydrate`
alone is canonical-cache restoration, not a serving semantic-index rebuild.

## Use the repaired kit now without rebuilding the application

The reported CPU installation already has the current serving application.
The sidecar capacity and frontend fixes are deployment templates, so a local kit
can pin the already installed immutable application while incorporating these
repairs. From the ProjectExpert checkout:

```bash
cd /home/dmytro/workspace/personal_projects/ProjectExpert/ProjectExpert
APP_IMAGE=ghcr.io/shkirmantsev/project-intelligence@sha256:c97d86439aa560c03077d3b353d98579eb1d47e92eeb58d35639e902001bdb93
docker build -f Containerfile --target deployment-kit \
  --build-arg PI_DEPLOY_IMAGE="$APP_IMAGE" \
  -t projectexpert-deployment:runtime-repair .
```

Back up/review the staged target changes first; the exporter backs up replaced
managed kit files too. Then explicitly upgrade the installed kit:

```bash
TARGET_REPO=/home/dmytro/workspace/personal_projects/trade-analyzer/trade-analyzer
docker run --rm -v "$TARGET_REPO:/deployment" \
  projectexpert-deployment:runtime-repair --upgrade
```

Default export still preserves every existing file. `--upgrade` replaces only
known kit templates, saves changed old templates under
`.project-intelligence-deploy/.kit-backups/upgrade-*/`, preserves `deployment.env`
and unrelated files, and refuses managed symlinks. It does not delete caches,
model volumes, accelerator state or project knowledge. Backups contain the
previous templates, including the old application pin, for manual rollback.
An upgrade replaces custom changes inside managed Compose files, so review the
backups; keep supported operator choices in `deployment.env`.

In the target's `.project-intelligence-deploy/deployment.env`, keep the existing
values and add the profile setting if Open WebUI is wanted:

```dotenv
PI_CONTROL_PORT=8766
PI_ACCELERATOR=cpu
COMPOSE_PROFILES=open-webui
```

Do not replace the whole environment file with this excerpt. If it contains a
`PI_IMAGE` override, that override takes precedence over the kit's embedded image
pin; retain or change it deliberately. For an authenticated ProjectExpert API,
set `PI_OPEN_WEBUI_API_KEY` to the operator's API bearer key privately. Otherwise
the default adapter placeholder key is sufficient. Review any other customized
settings from the backed-up Compose file. Move a cosmetic `WEBUI_NAME` to
`PI_WEBUI_NAME` in `deployment.env`; the kit maps it to the frontend environment.

Now restart once to apply the templates and retry bootstrap in the serving
process while retaining all data:

```bash
cd /home/dmytro/workspace/personal_projects/trade-analyzer/trade-analyzer/.project-intelligence-deploy
make platform-stop
make platform-start
```

After this one-time upgrade, normal startup remains just:

```bash
make platform-start
```

Do not use `down -v`, remove model volumes, delete `project-knowledge/`, or erase
the runtime cache. Indexing on CPU can take time; no generative LLM is required.
If a later refresh fails, fix its cause and use **Trigger reindex** in the web UI
so the job runs inside the serving process. Stopping/starting the service is also
a safe bootstrap retry. A 503 during an active refresh is expected.

## When using a newly published release

After CI publishes the repaired commit, use that commit's immutable **kit**
digest with `--upgrade` in the same export command. The published kit embeds the
matching immutable application digest. Do not substitute mutable `dev` or
`production` tags and do not claim the reported old kit digest contains this
repair. Native Windows launch-default changes require the new application too.

## Verify the target installation

```bash
curl -f http://127.0.0.1:8766/health/ready
curl -f http://127.0.0.1:8766/api/v1/indexing-status
curl -f http://127.0.0.1:8766/api/v1/sources
curl -f -X POST http://127.0.0.1:8766/api/v1/query \
  -H 'Content-Type: application/json' -d '{"text":"portfolio reconciliation"}'
curl -f http://127.0.0.1:8768/health
```

Use configured authentication privately if required. Check both browser pages:
[ProjectExpert](http://127.0.0.1:8766/) and
[Open WebUI](http://127.0.0.1:8768/). If an existing Open WebUI database retains an
older API connection, update its Admin Connections entry to
`http://production:8765/v1` and select `project-intelligence`; do not delete its
volume just to change an endpoint. The ProjectExpert UI's optional chat settings
can later connect LM Studio or Anthropic. An offline LM Studio is not a search
failure; disable optional chat until the provider is available.

The reported malformed `backtest_v4_modified.py` is target-project source code,
not an upstream ProjectExpert bug. It can remain an isolated parse failure until
the target owner fixes it. Remote GitLab fetch failures are separate host/repo
connectivity issues: indexing a local checkout does not require a remote fetch.
The displayed project version must accurately reflect that local checkout.

Existing `project-knowledge/project-context.yaml` is retained. Search can index a
project without automatically authoring Wiki articles. For a new project,
`make platform-init` is the explicit scaffolding action; review its changes.
PDF ingestion/chunking and curated Wiki authorship are separate operations.

## Follow-up verification on 2026-11-03

The attempted local upgrade was audited against the running trade-analyzer
installation. CPU runtime arguments are 4096/4096/4096; the application remains
pinned to the immutable digest above. Both HTTP health endpoints, REST search,
the OpenAI adapter and 27-tool MCP discovery passed. From inside Open WebUI,
model discovery and streaming completion through the internal adapter passed.
No external chat provider was enabled. A synthetic document was tokenized by
the actual running sidecar to 1507 tokens and embedded to a normalized 512d
vector successfully. This supplies real runtime evidence for the earlier
locally-unexecuted wide-input smoke, without changing its historical record.

The remaining operator-only Compose name mapping is now supported upstream as
`PI_WEBUI_NAME`. The target runbook/report must distinguish the original GHCR
kit from the locally rebuilt repair kit and must not retain obsolete destructive
cache-recovery or mandatory-chat-model instructions. The source parse failure
and host GitLab authentication issue remain separate target concerns.
