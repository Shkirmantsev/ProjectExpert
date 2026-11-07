# Fix deployment kit ownership

## Why
Root-run export repairs ownership only for a newly created directory. A pre-existing root-owned kit retains root ownership and preserved files, blocking normal-user editing and removal.

## What Changes
Repair root-owned kit directories, managed regular files and generated backups using the project owner's UID/GID. Preserve file contents, existing non-root ownership and link targets. Verify real root export followed by normal-user editing and removal.
