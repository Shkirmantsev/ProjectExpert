# Design

Infer ownership from the project parent for new/root-owned kits; retain an existing non-root kit owner. Apply root-only bounded metadata repair to the kit directory, known managed regular files and generated backup directories/files. Never recursively chown the project, follow symlinks or change unrelated entries. Run upgrade link validation before metadata mutations. Non-root exports retain normal filesystem behavior.
