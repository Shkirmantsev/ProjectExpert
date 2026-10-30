# Optional chat LLM and active embedding mode

ProjectExpert search uses embeddings independently of a chat LLM. You can now
add a real optional chat connection from the web UI. It generates explanations,
summaries and comparisons from retrieved project evidence. It does not grant
agent tool execution, code editing or automatic Wiki writes.

## Configure and test a chat model

Open section **11. Optional chat LLM — answers from project evidence**:

1. Choose **OpenAI-compatible** or **Anthropic Messages API**.
2. Enter the API **base URL**, including `/v1`, and the exact chat model identifier.
3. Enter a provider API key if the server requires authentication.
4. Check **Allow sending retrieved project excerpts to this endpoint**. This is
   explicit operator authorization for bounded context sharing to the saved
   endpoint. Existing egress classification rules still apply.
5. Check **Enable generated answers**, then **Save and apply**.
6. Click **Test saved connection**. It sends a small synthetic prompt, not project
   content, to verify that this endpoint/model can generate text. It may take up
   to 30 seconds. Test uses saved values; changing a field requires saving again.
7. Ask a project question in section 1. The generated answer appears above its
   source excerpts. **Run deterministic retrieval** continues to search without
   calling a chat model. Disable generated answers and save to return to search only.

| Provider | Example base URL | Model field |
| --- | --- | --- |
| LM Studio on the Docker host | `http://host.docker.internal:1234/v1` | Exact ID of a loaded **chat** model |
| Another OpenAI-compatible server | Reachable HTTP(S) API base ending in `/v1` | Server's chat model identifier |
| Anthropic | `https://api.anthropic.com/v1` | Available Claude model ID for your API account |

These are chat settings, separate from the managed Gemma embedding endpoint.
A Claude Code subscription/login is not an Anthropic API key or an HTTP model
server. Provider model/license/usage terms remain operator-owned; no new model
weights or provider SDK are bundled.

For LM Studio, start its API server and allow connections from Docker. A server
bound only to host `127.0.0.1` may not accept connections via the host gateway;
configure its listen address/authentication appropriately. The updated deployment
kit adds `host.docker.internal:host-gateway` for Linux; an existing kit needs that
`extra_hosts` entry under `production`, or use a reachable host LAN address.
Inside a container, `127.0.0.1` refers to that container. If using a direct
Open WebUI-to-LM Studio connection instead, configure reachability for the
Open WebUI container as well.

Settings apply immediately to this ProjectExpert server, including its Open
WebUI adapter. No image rebuild or restart is required **after the new application
version is deployed**. Settings live at
`.project-intelligence-cache/chat-settings.json`, are atomically saved with mode
0600 on POSIX, and are excluded from source discovery/Git. Keys never appear in
GET responses or browser storage. A blank key input keeps the saved key;
**Clear the saved provider key** removes it. UI access tokens remain separate
from provider API keys. Windows host ACL behavior depends on the runtime volume.

A failed/unauthorized/timed-out provider leaves retrieved evidence available and
adds a diagnostic. Model requests have a 30-second timeout, bounded evidence,
output tokens and response bytes; redirects are refused. The system does not
silently switch providers. A provider URL pointing back to ProjectExpert is
rejected instead of recursively requesting answers. External CONFIDENTIAL or
RESTRICTED context is not allowed by the normal saved INTERNAL sharing policy.

The implementation follows [LM Studio chat completions](https://lmstudio.ai/docs/developer/openai-compat/chat-completions)
and the [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages).
Anthropic requests use the established `2023-06-01` compatibility version header.

## Open WebUI

For the deployment kit's shared network:

```text
Connection URL: http://production:8765/v1
Model:          project-intelligence
```

This route retrieves ProjectExpert context and uses the optional saved chat
connection when enabled. Both non-streaming and finite SSE responses are
supported. A separate direct Open WebUI connection to LM Studio or another model
server bypasses ProjectExpert retrieval unless you separately integrate its tools.
Existing Open WebUI connection settings are not modified by saving this form.

## Active mode: CPU / GPU / Hybrid

The badge next to the embedding setup shows **active embedding execution**, not
whether a chat model is local/remote and not a guess based on GPU presence:

- **CPU**: loaded native model uses CPU, or the selected managed runtime is the
  CPU-only deployment profile.
- **GPU**: the loaded native embedding model uses CUDA/MPS.
- **Hybrid**: the selected managed CUDA/Vulkan embedding profile uses a GPU
  backend with the multimodal projector forced onto CPU. Its fit policy can
  also place model work on CPU. This describes the selected deployment profile;
  it does not claim a measured number of GPU-offloaded layers.
- **Unknown**: a remote/custom runtime supplies no reliable effective-device
  evidence. The UI explains that limitation instead of claiming Auto means GPU.

The badge includes backend, selected device when available, reason and evidence
source. The native adapter reports its loaded device and auto-selection reason.
The updated kit forwards `PI_INFERENCE_BACKEND` and `PI_GPU_DEVICE` from the
selected Compose overlay. Older managed kits using `http://embeddings:8769` can
report the overlay's effective `PI_EMBEDDING_DEVICE` as legacy evidence, even when
the UI's later requested device is Auto. Arbitrary remote servers are not inferred
from that setting.

Changing a UI device request does not recreate an external embedding sidecar.
Use the deployment launcher to select/change the managed hardware profile. Its
measured auto-selection and safe CPU fallback remain in effect.

## Upgrade an existing target

Build/redeploy the updated application as described in
[the container repair guide](CONTAINER_SEARCH_REPAIR.md). For a complete kit
upgrade preserve `deployment.env`, caches, and custom Open WebUI changes; merge
the new `extra_hosts` and effective-device environment fields from `compose.yaml`
and `compose.cpu.yaml` / `compose.cuda.yaml` / `compose.vulkan.yaml`.
Do not replace a target project's configuration wholesale.

## Configure before the first start with Make

Run these commands from the target's `.project-intelligence-deploy/` directory.
They use a one-shot application container; no host Python, serving process,
embedding startup or model download is required to save the chat configuration.

```bash
make platform-llm-configure \
  LLM_PROVIDER=openai \
  LLM_URL=http://host.docker.internal:1234/v1 \
  LLM_MODEL=your-loaded-chat-model \
  LLM_SHARE_CONTEXT=1
make platform-start
```

Alternatively, bind and start in one command:

```bash
make platform-start LLM=1 \
  LLM_PROVIDER=openai \
  LLM_URL=http://host.docker.internal:1234/v1 \
  LLM_MODEL=your-loaded-chat-model \
  LLM_SHARE_CONTEXT=1
```

`LLM=1` configures/enables before Compose `up`; invalid configuration stops the
start. Omitting `LLM` preserves the saved settings exactly. `LLM=0` disables chat
before starting and retains its endpoint/key. Once configured, `LLM=1` can reuse
saved endpoint/model/consent when those variables are omitted. A new configuration
requires explicit `LLM_SHARE_CONTEXT=1`; this authorizes bounded context sharing.
A supplied value of `0` does not silently authorize sharing.

For Anthropic use `LLM_PROVIDER=anthropic`,
`LLM_URL=https://api.anthropic.com/v1` and your available model identifier.
Provide authentication through the **environment**, not a key value on a Make
command line. For example, in Bash:

```bash
read -rsp 'Provider API key: ' LLM_API_KEY
printf '\n'
export LLM_API_KEY
# Run platform-llm-configure or platform-start LLM=1 with the non-secret values.
unset LLM_API_KEY
```

Only environment variable names are passed in the printed Docker command; the
CLI prints redacted settings. Blank/missing keys preserve a previously saved
key. Local servers without authentication need no key. `chat configure` also
supports `--api-key-stdin` for non-Make workflows; no secret CLI argument exists.

Additional commands work both before and after starting the service:

```bash
make platform-llm-status
make platform-llm-test
make platform-llm-disable
```

The test command contacts the saved provider with a synthetic prompt and sends
no project context. Configuration itself performs no provider request.
**Make and the UI share the same settings file**: the URL/model saved at startup
appear in section 11, can be edited there, and UI changes apply immediately.
There is no environment override that resets them when the browser saves or the
container restarts. The provider key stays hidden.

Existing target kits must update their Makefile and application image before
these new commands are available. Preserve local `deployment.env` and custom
sidecar settings during the upgrade.
