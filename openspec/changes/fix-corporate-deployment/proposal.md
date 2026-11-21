# Repair corporate deployment and source recovery

## Why

On Windows, the published kit mapped the Docker host name to the VM gateway even
when the engine provided a working host name. Fixed inference ports and a
managed key also made operator recovery difficult. An indexing failure could
report a count without identifying the affected files, and encoding review in
the web UI required editing JSON.

## What changes

- Verify the Windows native embedding route from the production network and
  use the validated endpoint for application startup.
- Offer a custom llama-server port and an explicit tokenless mode for the
  unpublished managed sidecar. Preserve authentication on the native listener.
- Connect an existing native Windows server on the local Docker bridge, with
  a private token file or an explicitly tokenless private listener.
- Prepare pinned GPU libraries and refresh trusted host roots through the
  existing kit. Reuse Docker and the packaged application.
- Show a private diagnostic of the last source pass and provide form controls
  for reviewed encoding rules.

## Impact

The kit and application image must be upgraded together. Existing saved
source rules, version fences, deployment environments and model identities are
compatible. Completing the corporate recovery design also requires physical
host acceptance and partial query readiness.
