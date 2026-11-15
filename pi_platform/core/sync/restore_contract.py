"""Restore-only refusal retains imported cache data and the prior activation."""


class RestoreRequiresReindex(RuntimeError):
    def __init__(self, message, *, report=None):
        super().__init__(message)
        self.report = dict(report or {})
