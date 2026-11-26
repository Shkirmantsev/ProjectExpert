# Verification

The HTTP fixture reproduced 401 responses on viewer routes with an admin
token configured. The browser test reproduced administrative controls loading
before authorization.

Focused HTTP tests verify viewer retrieval and status, 401 for privileged
actions, and access with the matching bearer. The browser test verifies that
a viewer can browse, an incorrect token keeps controls hidden, and the
matching token reveals them.
