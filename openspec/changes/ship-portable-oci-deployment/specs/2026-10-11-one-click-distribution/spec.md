## ADDED Requirements

### Requirement: Standalone deployment kit
The platform MUST publish a matching deployment kit in GHCR with Compose,
ready-to-start non-secret defaults, product-only Make targets, and Linux and
Windows startup entry points. Installing the kit MUST preserve existing files.

#### Scenario: First startup without a checkout
Given Docker and an existing target repository on Linux or Windows
When the operator downloads and starts the deployment kit
Then the production image starts and automatically obtains its pinned embedding
model in persistent storage, without host Python or the development harness.
And success is reported only after retrieval readiness.

#### Scenario: Reinstall preserves configuration
Given an existing deployment.env with operator settings
When the kit is exported again
Then deployment.env is not replaced.

### Requirement: Verified development artifacts
A push or merge to dev, development or main MUST publish the verified production image
and a deployment kit referencing that image's immutable digest. A pull request
MUST verify without publishing. Unaccepted dependency reviews MUST block release.

#### Scenario: Failed readiness prevents publication
Given a built candidate whose model cannot load
When the release smoke check runs
Then publication fails before updating development tags.

### Requirement: GPU-independent default
The default deployment MUST run real embedding inference on CPU without requiring
CUDA or Vulkan drivers. Documentation MUST distinguish compatibility with hosts
having office graphics from GPU-accelerated inference.

#### Scenario: No accelerator available
Given a Linux or Windows host with no supported GPU passthrough
When the default deployment starts
Then the selected real embedding model executes on CPU.

### Requirement: Optional real GPU embeddings
The kit MUST provide both CPU execution and optional Gemma or Qwen GGUF Vulkan or CUDA
execution. Windows GPU setup MUST obtain a pinned native runtime and model
without a separate manual download. Linux MUST use pinned runtime images.
Gemma image embeddings and Docling OCR MUST remain available in the CPU profile.

#### Scenario: Initial assets prepared automatically
Given a clean cache, access to the selected model, and a repository containing PDFs
When production setup starts
Then the selected embedding model and required Docling layout, table and OCR assets are
obtained automatically before retrieval readiness.
And code-only repositories do not download document assets.

#### Scenario: Unsupported GPU
Given no usable selected GPU device
When the GPU deployment starts
Then setup fails with a diagnostic rather than claiming accelerated success.

### Requirement: Versioned deployment retention
Published runtime and kit artifacts MUST have commit-specific tags with no
configured automatic expiry. Deployment source files MUST remain in Git.

#### Scenario: Branch advances
Given a previously published commit
When a new commit updates its branch alias
Then the old commit-specific tag remains available unless explicitly deleted.

### Requirement: Independent model and device selection
The deployment MUST preserve the operator's choice of Gemma or Qwen across CPU,
Vulkan and CUDA modes. GPU setup MUST obtain the matching pinned GGUF assets;
Gemma MUST include its multimodal projector and accept image bytes. CPU MUST
remain available for both models without a GPU prerequisite. GGUF and PyTorch
profiles MUST NOT reuse incompatible vectors.

#### Scenario: Gemma on GPU
Given PI_EMBEDDING_MODEL=gemma and PI_ACCELERATOR=vulkan or cuda
When the deployment is started
Then setup obtains Gemma's pinned model and projector and selects Gemma GGUF.
And image inputs are sent to the multimodal encoder, not discarded.

#### Scenario: Qwen explicitly on CPU
Given PI_EMBEDDING_MODEL=qwen and PI_ACCELERATOR=cpu
When the deployment is started
Then Qwen runs on CPU with no GPU runtime or GPU device requirement.
