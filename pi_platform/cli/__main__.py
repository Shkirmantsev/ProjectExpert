"""Allow ``python -m pi_platform.cli`` to invoke the CLI."""

from .main import main

raise SystemExit(main())