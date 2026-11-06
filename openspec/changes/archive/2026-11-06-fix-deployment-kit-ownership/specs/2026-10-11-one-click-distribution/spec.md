## ADDED Requirements

### Requirement: User-owned exported deployment kit
On POSIX filesystems, root-run export SHALL assign a new or existing root-owned kit directory to its target project parent's UID/GID and repair root-owned managed regular files and generated backups. Existing non-root kit ownership SHALL be retained. Ordinary users SHALL be able to edit the kit and remove it after export. Repair SHALL preserve operator contents, skip link targets and unrelated entries, and SHALL NOT recursively change project ownership.

#### Scenario: Root-owned kit exists before setup
- **GIVEN** a user-owned target project with an existing root-owned deployment kit
- **WHEN** the root-run container exports or upgrades the kit
- **THEN** the project user can edit preserved deployment.env and remove the kit, while unrelated files and link targets retain ownership and content
