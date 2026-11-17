## ADDED Requirements

### Requirement: Optional verified Windows CUDA runtime
The Windows launcher SHALL support an independently verified offline CUDA runtime
when the Docker engine cannot expose NVIDIA devices, while keeping the standard
Vulkan/model asset pack unchanged. The pack SHALL bind to the exact primary
manifest and pinned runtime, reject unsafe Windows paths and unreviewed content,
and install atomically without modifying complete local source/embedding caches.

#### Scenario: Rancher engine lacks CUDA passthrough
- **WHEN** an approved matching native CUDA pack is configured and native CUDA
  reports a usable selected device
- **THEN** the launcher starts the verified native host server and uses its
  authenticated endpoint without installing a toolkit or replacing drivers.

#### Scenario: Missing or invalid optional pack
- **WHEN** CUDA content is absent, corrupt, incompatible or unapproved
- **THEN** no executable from that pack runs, a specific cause is retained, and
  auto may use verified Vulkan or CPU; explicit CUDA uses CPU or strict failure.

### Requirement: Reliable Windows probe and release gate
Short-lived native probes SHALL preserve integer exit codes and both output
streams, time out with owned-child cleanup, and run under PowerShell5.1 and7.
Production promotion SHALL require the same complete launcher acceptance suite.

#### Scenario: Immediate failure with stderr
- **WHEN** a verified probe exits23 and writes stderr
- **THEN** its result retains23 and stderr and does not mutate caller preferences.
