"""Error type for the workspace CLI."""
from __future__ import annotations


class WsError(Exception):
    """A user-facing failure.

    ``phase`` names the operation stage that failed (e.g. "preconditions",
    "materialize"), which fork/merge report to make partial failures diagnosable.
    """

    def __init__(self, message: str, phase: str | None = None, code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.phase = phase
        self.code = code

    def __str__(self) -> str:
        if self.phase:
            return f"{self.message} (phase: {self.phase})"
        return self.message
