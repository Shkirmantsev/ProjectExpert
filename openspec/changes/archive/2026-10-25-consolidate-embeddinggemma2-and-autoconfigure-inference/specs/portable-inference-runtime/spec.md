## ADDED Requirements

### Requirement: portable inference runtime policy

The platform MUST own the inference runtime policy in one place: backend
discovery, device selection, the launch flags and the degradation behaviour.
The platform MUST offer a documented command that reports the detected
hardware, the validated backends, the selected profile and the reason a
candidate was rejected, without starting the application.

The decision MUST be derived from evidence produced by the runtime itself.
The presence of a GPU vendor tool on the host MUST NOT by itself be treated
as proof that the backend is usable.

#### Scenario: CPU-only host selects the CPU profile

Given a Linux or Windows host with no supported GPU device
When the operator asks for the inference diagnostics
Then the report names the CPU profile as selected
And the report lists each rejected GPU candidate with its reason
And the report never claims GPU acceleration

#### Scenario: unavailable GPU degrades instead of failing

Given a host where the selected GPU backend cannot be validated
When the deployment starts
Then the deployment uses the validated CPU profile
And the application starts and serves normally
And the downgrade is reported to the operator

#### Scenario: a software rasteriser is never selected

Given a Vulkan loader that reports only a software device
When the backends are probed
Then the Vulkan candidate is rejected with an explicit software-device reason
And the CPU profile is used

### Requirement: a GPU is selected only when it is measurably faster

The platform MUST measure the CPU baseline and every validated GPU
candidate with the same fixed corpus before it selects a backend. A GPU
candidate MUST only be selected when it is at least 1.10 times faster
than the CPU baseline; a GPU that works but is slower MUST be rejected
and the CPU profile MUST be used.

The device memory the runtime reports is the FREE figure. The memory
fit budget MUST be computed from the free memory only: a budget derived
from the total memory would promise memory the runtime cannot use.

An explicitly selected backend is the operator's decision and MUST NOT
be second-guessed by the benchmark; it MUST still be validated, and an
invalid one MUST degrade to the CPU profile.

#### Scenario: a slower GPU is rejected in favour of the CPU baseline

Given a host whose validated GPU profile is slower than the CPU baseline
When the launcher selects the backend
Then the GPU candidate is rejected with the measured speed-up as the reason
And the CPU profile is used
And the measured latencies are reported

#### Scenario: a faster GPU is selected

Given a host whose validated GPU profile is measurably faster than the CPU
baseline
When the launcher selects the backend
Then the GPU profile is selected
And the device and the memory fit budget are applied

#### Scenario: the fit budget uses the free memory

Given a runtime that reports the total and the free device memory
When the memory fit budget is computed
Then the budget is computed from the free memory

### Requirement: explicit runtime arguments

The platform MUST pass inference runtime flags as an explicit argument
vector to the runtime process. The platform MUST NOT rely on environment
variables whose names are specific to one runtime version, because such names
differ from the flag names and are silently ignored when they do not match.

The reference CPU profile MUST disable GPU device use entirely, MUST keep the
multimodal projector off the GPU, and MUST bound the context, batch and
parallel settings.

#### Scenario: the requested batch policy reaches the runtime

Given a deployment that requests a physical batch size
When the runtime starts
Then the runtime log reports the requested physical batch size
And the runtime log does not report a different default value

#### Scenario: the CPU profile cannot use a GPU

Given the CPU profile on a host that has a GPU
When the runtime starts
Then the runtime is started with GPU devices disabled
And the multimodal projector is not offloaded to the GPU

### Requirement: one embedding model

The platform MUST offer exactly one production embedding model. The retired
alternative model MUST NOT remain selectable, MUST NOT remain in the licence
inventory as a production-enabled record, and MUST NOT remain part of a
deployment setup option. Selecting a retired alias MUST fail with an
actionable message naming the supported alias.

Retiring an alias MUST NOT delete any stored vector data.

#### Scenario: the retired alias is rejected with guidance

Given an operator configuration that still names the retired model alias
When the runtime configuration is resolved
Then resolution fails with an actionable error naming the supported alias
And no embedding backend is silently substituted

#### Scenario: retiring an alias keeps stored vectors

Given an existing dense index built with the retired model
When the alias is retired
Then the stored vectors remain on disk
And the retired vector space is never merged with the current one
