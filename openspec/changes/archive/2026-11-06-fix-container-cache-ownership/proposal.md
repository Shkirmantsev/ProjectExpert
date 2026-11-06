# Fix container cache ownership

## Why
Root-run application processes create root-owned project cache files even if the directory was repaired once. Normal project users must own and manage both existing cache and newly generated runtime state.

## What Changes
- Prepare existing root-owned private cache safely at container startup.
- Run application CLI handlers with the target project UID/GID, automatically in container images.
- Retain access to the dedicated model volume/cache and internal embedding key.
- Keep host CLI behavior, canonical source ownership and external link targets unchanged.
