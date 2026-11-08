# Prevent deployment ownership regressions

## Why
An existing kit can retain an image pin from before project-owner execution was implemented. Merely restarting that image recreates root-owned cache and private Wiki files. Wiki atomic replacements also reset existing access modes to the temporary file's 0600.

## What Changes
- Guard application startup in Compose before CLI writers run, including when deployment.env is omitted or PI_IMAGE overrides the kit pin.
- Keep parameter-free startup and matching published image pins.
- Create new atomically written Wiki pages with 0644 and preserve existing ordinary permission bits on update.
- Exercise these contracts against the real candidate image and exported kit before publication.
