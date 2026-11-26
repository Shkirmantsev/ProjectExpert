# Verification

The old wildcard startup refusal and false remote authorization status were reproduced before implementation.

Three isolated Docker containers verified a remote address with the token absent, empty and configured. Tokenless settings writes and a scoped approval grant succeeded. The configured-token case returned 401 for missing or wrong credentials and accepted the matching bearer. Cross-origin tokenless writes were denied.

Python HTTP, browser JavaScript and PowerShell 7 launcher fixtures also passed.
