"""Monotonic request deadline budget management."""
from __future__ import annotations

import time
from typing import Optional

from promption.llm.exceptions import LLMTimeoutError


class RequestDeadline:
    """Tracks a monotonic deadline across multi-step pipeline executions."""

    def __init__(self, timeout_seconds: float | None = None, total_seconds: float | None = None):
        val = timeout_seconds if timeout_seconds is not None else total_seconds
        if val is None or val <= 0:
            raise ValueError("Timeout budget must be greater than zero")
        self.budget_seconds = float(val)
        self.start_time = time.monotonic()
        self.deadline = self.start_time + self.budget_seconds

    @property
    def total_seconds(self) -> float:
        """Total configured budget in seconds."""
        return self.budget_seconds

    @property
    def remaining(self) -> float:
        """Remaining seconds before the deadline expires (monotonically decreasing, never negative)."""
        rem = self.deadline - time.monotonic()
        return max(0.0, rem)

    @property
    def is_expired(self) -> bool:
        """True if the deadline has expired."""
        return self.remaining <= 0.0

    @property
    def elapsed(self) -> float:
        """Elapsed seconds since the deadline was initiated."""
        return time.monotonic() - self.start_time

    def check_expired(self, step_name: str | None = None) -> None:
        """Raises LLMTimeoutError if the deadline has already passed."""
        if self.is_expired:
            msg = f"Request deadline exceeded ({self.budget_seconds:.1f}s total budget)"
            if step_name:
                msg += f" during '{step_name}'"
            raise LLMTimeoutError(msg)

    def remaining_for_step(self, max_step_timeout: Optional[float] = None, step_name: str | None = None, step_limit: Optional[float] = None) -> float:
        """Returns the bounded remaining seconds for a single sub-step without exceeding overall deadline."""
        self.check_expired(step_name)
        rem = self.remaining
        limit = max_step_timeout if max_step_timeout is not None else step_limit
        if limit is not None and limit > 0:
            return min(rem, float(limit))
        return rem
