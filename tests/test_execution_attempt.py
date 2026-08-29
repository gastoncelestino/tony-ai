"""Tests for execution Attempt/Result observation contracts."""
from __future__ import annotations

import pytest

from kernel.execution_attempt import ExecutionAttempt, ExecutionAttemptError, ExecutionResult


def test_started_attempt_is_running_and_has_call_id():
    attempt = ExecutionAttempt.started(
        project_id="p1", session_id="s1", call_id="call-1",
        task_id="T1", phase="apply", started_at="2026-08-29T10:00:00+00:00",
    )
    assert attempt.status == "running"
    assert attempt.call_id == "call-1"
    assert attempt.result is None


def test_after_result_transitions_attempt_to_succeeded():
    attempt = ExecutionAttempt.started(
        project_id="p1", session_id="s1", call_id="call-1",
        task_id="T1", phase="apply", started_at="2026-08-29T10:00:00+00:00",
    )
    result = ExecutionResult("Task", "done", {"exit_code": 0})
    finished = attempt.succeeded(result, finished_at="2026-08-29T10:00:01+00:00")
    assert finished.status == "succeeded"
    assert finished.result == result
    assert finished.finished_at == "2026-08-29T10:00:01+00:00"
    assert finished.task_id == "T1"


def test_running_attempt_cannot_have_result():
    with pytest.raises(ExecutionAttemptError):
        ExecutionAttempt(
            "p1", "s1", "c1", "T1", "apply",
            started_at="now", result=ExecutionResult("Task", "done", {}),
        )


def test_succeeded_attempt_requires_result():
    with pytest.raises(ExecutionAttemptError):
        ExecutionAttempt("p1", "s1", "c1", "T1", "apply", status="succeeded", started_at="now")


def test_result_requires_complete_after_hook_shape():
    with pytest.raises(ExecutionAttemptError):
        ExecutionResult.from_mapping({"title": "Task", "output": "done"})


def test_attempt_does_not_authorize_task_completion():
    attempt = ExecutionAttempt.started(
        project_id="p1", session_id="s1", call_id="c1", task_id="T1", phase="apply"
    ).succeeded(ExecutionResult("Task", "done", {}))
    assert attempt.status == "succeeded"
