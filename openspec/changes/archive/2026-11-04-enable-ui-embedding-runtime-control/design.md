# Design

The model-setup container prepares a stdlib-only Python bundle from the pinned
application in the model volume, without copying application dependencies. The
sidecar's shell entrypoint uses that bundle and preserves inherited dynamic
library paths; it does not assume a system Python in CUDA/Vulkan images. Device
probing bypasses Python so fresh-cache startup can discover hardware before setup.
UI jobs run through the version monitor's serialized refresh/publication path;
the accepted snapshot becomes its baseline before job completion, preventing a
second refresh immediately after the UI reports success.

A stdlib Python supervisor in the pinned Linux embedding image owns only its llama-server child. The kit mounts the supervisor read-only; an authenticated internal HTTP control port accepts bounded device selections, not commands or paths. The application reuses the inference selection policy and benchmarks Auto against CPU before selecting GPU. Failed child startup restores the prior child configuration and indexing fails closed. CPU/Vulkan/CUDA choices are limited to devices exposed to the existing container; Linux launchers expose /dev/dri when present, including when initial selection is CPU. No Docker socket is mounted.

Explicit UI model/device intent is stored in ignored cache state and reloaded as an operator command override. Native Transformers selections use the existing factory and download workflow; managed GGUF selections configure the child before indexing. Cache vectors/knowledge remain intact. Status reports observed supervisor backend, selected device, request and reason, separately from cached settings. The UI obtains available choices, applies settings through observable jobs and shows switching/failure before readiness. Legacy/native-Windows remote deployments without a supervisor receive actionable capability limits, not a fake switch. Native Windows GPU process control is not added in this slice; Linux managed runtime and native in-process bindings are covered.

Public authentication metadata exposes only whether PI_UI_TOKEN is configured. The token is an operator-defined API bearer secret, never an LLM key and never generated or returned by this endpoint. Local loopback deployment remains optional-auth by default; configured API authorization remains enforced for control operations.
