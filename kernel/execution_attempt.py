"""Execution attempt/result model for the Tony Kernel boundary.

An Attempt records an execution observation correlated by OpenCode callID.
It does not authorize completion and never mutates TaskSet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


class ExecutionAttemptError(ValueError):
    """Raised when an execution attempt/result is invalid."""


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Observed result of an OpenCode tool execution."""

    title: str
    output: str
    metadata: Any

    def __post_init__(self) -> None:
        if not isinstance(self.title, str):
            raise ExecutionAttemptError("result title must be a string")
        if not isinstance(self.output, str):
            raise ExecutionAttemptError("result output must be a string")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExecutionResult":
        if not isinstance(value, Mapping):
            raise ExecutionAttemptError("result must be an object")
        required = ("title", "output", "metadata")
        if any(key not in value for key in required):
            raise ExecutionAttemptError("result is missing required fields")
        return cls(value["title"], value["output"], value["metadata"])

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "output": self.output, "metadata": self.metadata}


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    """Immutable observation of one authorized tool execution."""

    project_id: str
    session_id: str
    call_id: str
    task_id: str
    phase: str
    status: str = "running"
    started_at: str = ""
    finished_at: str | None = None
    result: ExecutionResult | None = None

    def __post_init__(self) -> None:
        for field_name in ("project_id", "session_id", "call_id", "task_id", "phase"):
            if not getattr(self, field_name).strip():
                raise ExecutionAttemptError(f"{field_name} must be non-empty")
        if self.status not in {"running", "succeeded", "failed", "incomplete"}:
            raise ExecutionAttemptError(f"Invalid attempt status: {self.status}")
        if self.status == "running" and self.result is not None:
            raise ExecutionAttemptError("running attempt cannot have a result")
        if self.status in {"succeeded", "failed"} and self.result is None:
            raise ExecutionAttemptError(f"{self.status} attempt requires a result")

    @classmethod
    def started(
        cls,
        *,
        project_id: str,
        session_id: str,
        call_id: str,
        task_id: str,
        phase: str,
        started_at: str | None = None,
    ) -> "ExecutionAttempt":
        return cls(project_id, session_id, call_id, task_id, phase, started_at=started_at or now())

    def succeeded(self, result: ExecutionResult, *, finished_at: str | None = None) -> "ExecutionAttempt":
        return self._finished("succeeded", result, finished_at)

    def failed(self, result: ExecutionResult, *, finished_at: str | None = None) -> "ExecutionAttempt":
        return self._finished("failed", result, finished_at)

    def incomplete(self, *, finished_at: str | None = None) -> "ExecutionAttempt":
        return ExecutionAttempt(
            self.project_id, self.session_id, self.call_id, self.task_id, self.phase,
            "incomplete", self.started_at, finished_at or now(), None,
        )

    def _finished(
        self,
        status: str,
        result: ExecutionResult,
        finished_at: str | None,
    ) -> "ExecutionAttempt":
        return ExecutionAttempt(
            self.project_id, self.session_id, self.call_id, self.task_id, self.phase,
            status, self.started_at, finished_at or now(), result,
        )


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
