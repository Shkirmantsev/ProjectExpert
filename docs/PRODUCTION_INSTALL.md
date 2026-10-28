# Install and launch

The core package needs Python 3.11 or newer and has no runtime dependencies.
Semantic production additionally needs the pinned embedding, USearch and Docling
stack. Model weights are downloaded automatically during container setup and kept across restarts.

From a source checkout, on Linux x86_64 with Python 3.11:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-production-linux-x86_64.txt -r requirements-production-java-linux-x86_64.txt
.venv/bin/python -m pip install --no-deps '.[production]'
.venv/bin/python -m pip check
.venv/bin/python -m pi_platform.cli start --target /path/to/repository --model gemma-torch --device cpu --serve
```

The hash lock is resolved for CPython 3.11 on Linux x86_64 and uses CPU PyTorch.
Installation and dependency/import checks also pass on CPython 3.12.3; this does
not replace the separate real-model and PDF acceptance gates.
Other Python versions, macOS, Windows, and CUDA installations can install
`python -m pip install '.[production]'` in a virtual environment; this pins direct
dependencies, but is not the same verified transitive lock. Resolve and verify a
platform-specific lock before redistribution. The lightweight package installs
with `python -m pip install .` and requires the explicit minimal startup profile.

With Docker Compose, from this checkout:

```bash
PI_TARGET_REPO=/path/to/repository PI_EMBEDDING_MODEL=gemma-torch docker compose --profile production up -d --build
```

Open `http://localhost:8765`. The production image is Linux x86_64; Docker Desktop
on other architectures requires amd64 emulation. Compose persists the Hugging
Face model cache in `pi-model-cache`. The first startup needs network access,
disk space for Python packages and model weights, and time to download them.
Google model access may require accepting its
license and exporting `HF_TOKEN` in your shell. Credentials are passed at runtime
and never baked into the image. See the model provider's current access terms.

Build distinct artifacts:

```bash
docker build -f Containerfile --target production -t project-intelligence:production .
docker build -f Containerfile --target core -t project-intelligence:core .
```

The production target installs the complete hash-checked closure then runs
`pip check`. The core target has no embedding/Docling dependencies and starts in
minimal mode. `docker compose --profile core-headless up -d --build` selects it.
Models are not part of either image. A successful image build proves dependency
installation, not model inference or semantic relevance; run the production
release gate separately.

To regenerate the Linux lock after reviewing dependency changes, use uv:

```bash
uv pip compile pyproject.toml --extra production --python-version 3.11 --python-platform x86_64-unknown-linux-gnu --no-build --no-python-downloads --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match --generate-hashes --emit-index-url --output-file requirements-production-linux-x86_64.txt
```

Package hashes authenticate the resolved artifacts even though resolution uses
two public indexes. Review version and license inventory changes, build the
production image, and run real model/PDF tests before publishing a regenerated
lock. Air-gapped deployments must preload both the locked wheel closure and all
selected model snapshots; image availability alone does not provide weights.

The reviewed production closure is tracked separately from the core inventory.
Rebuild its wheel metadata evidence inside the installed locked environment with
`python scripts/production_dependency_inventory.py`. The
[license review](PRODUCTION_LICENSE_REVIEW.md) records operator acceptance of the
exact 12-coordinate closure on 2026-10-22; changed inputs still block builds.
The default allow/review policy has not been expanded. SPDX expressions preserve
AND/OR obligations and treat WITH exceptions as separately reviewed identities.

For a container deployment, use `make pi-model DOCKER=1 MODEL=gemma-torch` to recreate
the production service with the selected model. `make pi-status DOCKER=1`,
`make pi-reindex DOCKER=1`, and `make pi-doctor DOCKER=1` execute in that service.
Model data remains in the persistent named cache volume.


Evaluate an installed repository with the same runtime used by UI and MCP:

```bash
.venv/bin/python -m pi_platform.cli eval-retrieval --target /path/to/repository --golden /path/to/golden.yaml --no-baseline --out /path/to/report.json
```

Golden labels must reference the repository's actual canonical chunk IDs. Omit
`--target` to run the separate bundled fixture benchmark. See
[executed acceptance and limits](PRODUCTION_RECONCILIATION_STATUS.md) before
claiming container or cross-platform readiness.

## Standalone GHCR deployment kit

The `publish-oci-container` workflow prepares two artifacts on dev, development,
and main pushes/merges after
product checks: `project-intelligence:sha-<full-commit>` and
`project-intelligence-deployment:sha-<full-commit>`. The kit pins the tested image
digest. Each receives its publishing branch alias (`dev`, `development`, or `main`);
the runtime also receives `production`. PR runs build and test without publishing. Publication requires the approved exact dependency review and a passing
container smoke check. These are deployment instructions for the resulting artifacts,
not a claim that this checkout has already published them.

With Docker installed and running, execute from the target repository.
Linux (Docker Engine with Compose 2.20+):

```bash
docker run --pull=always --rm -v "$PWD:/deployment" ghcr.io/shkirmantsev/project-intelligence-deployment:dev && bash .project-intelligence-deploy/start.sh
```

Windows PowerShell 5.1 or 7 (Docker Desktop, WSL2, Linux containers):

```powershell
docker run --pull=always --rm -v "${PWD}:/deployment" ghcr.io/shkirmantsev/project-intelligence-deployment:dev; if ($LASTEXITCODE -eq 0) { & .\.project-intelligence-deploy\start.ps1 }
```

Windows execution policy must permit local scripts. No host Python, Git checkout
of ProjectExpert, ORAS, or GNU Make is required for these entry points. If GHCR
package visibility is private, authenticate with `docker login ghcr.io` first.
The publisher must configure package visibility/access in GitHub; CI does not
silently change it.

The kit exports `compose.yaml`, `deployment.env`, `Makefile`, `start.sh`,
`start.ps1`, `url.sh`, `url.ps1`, and `README.md` under
`.project-intelligence-deploy`. Existing files are preserved. Run
`make -C .project-intelligence-deploy platform-start` if GNU Make is
available, or use its `platform-status`, `platform-logs`, `platform-stop`,
`platform-models`, `platform-doctor`, `platform-reindex`, and `eval-*` targets.
A bare `make` (or `make help`) only prints the command list: it starts
nothing and needs neither Docker nor Python. Edit `deployment.env` for a
different repository, model or port; the shell environment overrides it. The
repository must exist; Compose does not silently create a misspelled mount path.

The kit defaults to EmbeddingGemma 2 Q8_0 through a managed llama.cpp runtime,
with pinned model and multimodal projector downloads on first startup. Weights and document-processing caches persist in a
named volume. The launcher waits up to 30 minutes for retrieval readiness;
liveness does not count as successful setup. `platform-stop` retains the cache.
The UI binds to localhost by default. Export credentials through your shell;
none are shipped in the kit. After an upgrade, compare the new kit in a separate
directory and update the existing Compose image digest explicitly.

### Ensure you receive the merged revision

Wait for the merge commit's **Verify and publish production with deployment kit**
job in `publish-oci-container` to finish successfully. The core image publishes
independently and does not prove production publication has finished. A merge
starts the workflow; the previous branch aliases remain available until the
new production image passes its checks and is published.

The setup commands above use `--pull=always`: without it, `docker run` can use an
older locally cached `:dev` kit indefinitely. Inspect the registry without relying
on the local image cache:

```bash
docker buildx imagetools inspect ghcr.io/shkirmantsev/project-intelligence:dev
docker buildx imagetools inspect ghcr.io/shkirmantsev/project-intelligence-deployment:dev
# Read the image reference shipped in the current kit without changing any files:
docker run --pull=always --rm --entrypoint cat ghcr.io/shkirmantsev/project-intelligence-deployment:dev /bundle/compose.yaml
```

For an **existing** installation, pulling a new kit does not replace exported
files. `Preserved compose.yaml` means the previous image pin is still in use.
Export into a fresh staging directory from your target repository instead:

```bash
mkdir -p .project-intelligence-upgrade
docker run --pull=always --rm -v "$PWD/.project-intelligence-upgrade:/deployment" ghcr.io/shkirmantsev/project-intelligence-deployment:dev
```

Use a fresh staging directory for each upgrade. Compare its
`.project-intelligence-deploy/` files with your installed kit. Adopt the new
Compose image digest and relevant launcher/configuration changes while preserving
local ports, target paths, accelerator settings and patches. An existing `PI_IMAGE`
in `deployment.env` or your shell overrides the Compose image: update or remove
that override deliberately. `PI_DEPLOY_IMAGE` is a kit **build argument**, not the
runtime override.

For an image-only upgrade, set `PI_IMAGE=ghcr.io/shkirmantsev/project-intelligence@sha256:<digest>`
in your existing `deployment.env`, using the digest from the new kit. Then run
`bash .project-intelligence-deploy/start.sh` (Windows: run its `start.ps1`).
Compose recreates the service when its image changes and keeps the model cache.
Keep your previous digest/configuration for rollback. Running `docker restart`
alone does not change the image. Do not use `down -v` to upgrade.

### Hardware and model selection

See the [deployment kit guide](../distribution/deployment/README.md) for defaults,
GPU prerequisites, Windows lifecycle and firewall scope. Set PI_ACCELERATOR in
`deployment.env` or your shell before running the same start command:

| Selection | Linux x86_64 | Windows x86_64 / Docker Desktop |
|---|---|---|
| auto (default) | Probe CUDA/Vulkan and compare usable inference with CPU | Probe native CUDA/Vulkan and compare with container CPU |
| cpu | Managed Gemma Q8_0 CPU sidecar | Same Linux services via WSL2 |
| vulkan | Gemma sidecar using /dev/dri | Native Gemma service with compatible Vulkan drivers |
| cuda | Gemma sidecar with NVIDIA Container Toolkit | Native Gemma service with compatible NVIDIA drivers |

GPU selection requires a usable runtime device and successful inference. Automatic
selection requires measured improvement over CPU; unavailable or failed candidates
fall back to CPU. Integrated GPUs require compatible Vulkan drivers; basic display
and software rasterizer drivers are not evidence of usable acceleration. CPU thread counts and GPU fit margins come from the runtime plan. The fit
margin is reserved headroom, not a hard GPU memory consumption limit. Docling OCR remains on CPU.
The standalone application container uses `gemma-torch`; the deployment kit uses
`gemma` with its managed GGUF service. Repository images and retained PDF figures
are supported; audio/video repository ingestion is not exposed. Changing runtime
profile creates a distinct vector namespace.

Selected model weights are prepared automatically. Pinned Docling layout/table/OCR assets are prepared only for PDF inputs
automatically before initial retrieval readiness. No separate model download
command is required. Provider access terms may still require user acceptance.
Physical Vulkan/CUDA execution and Windows Docker Desktop were not available
in the local verification environment; do not treat these configurations as
universal hardware certification. ARM is not validated.

The runtime and kit have commit SHA tags and branch aliases. No expiry or package
cleanup is configured. Deployment sources remain in Git history after merge.
GitHub owners can delete packages or repositories; archive required releases
independently if retention must survive that. These local changes must still be
merged and the publishing workflow must succeed before GHCR downloads exist.

## Clean external-repository installations

The deployment kit defaults to `PI_EMBEDDING_MODEL=gemma` and
`PI_ACCELERATOR=auto`. `gemma-gguf` is an alias for the same pinned model.
Native `gemma-torch` is available for direct Python/container execution.
PDF/OCR assets download only for repositories containing PDFs. See the
[deployment guide](../distribution/deployment/README.md) for device selection,
cache cleanup and upgrading an existing exported kit.

Python manifests, source and wheel libraries can be indexed without installing
or importing their code. See [Python dependency analysis](PYTHON_DEPENDENCY_ANALYSIS.md).

Production installs `requirements-production-java-linux-x86_64.txt` in addition
to the original dependency lock. This adds only `tree-sitter-java==0.23.5` (MIT)
against the existing tree-sitter 0.26.0 runtime. Its separate inventory and gate
preserve the exact prior production review; the build executes a real Java parse.

MCP uses stateless Streamable HTTP at `/mcp`, with standard initialize metadata,
argument schemas, empty 202 notification acknowledgements, and 405 for GET streams.
Use a Streamable HTTP client, not a legacy SSE-only client.
