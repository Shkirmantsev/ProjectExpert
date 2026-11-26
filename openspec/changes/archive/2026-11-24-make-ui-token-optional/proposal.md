# Make the UI token optional

## Why

An absent token is the operator's choice to give ordinary users full application access on the configured listener. The previous local bootstrap prevented this on remote addresses.

## What Changes

Grant application administration without a sign-in when the token is unset or empty, across local and remote interfaces. Preserve same-origin browser writes, role restrictions and operation-specific approvals.
