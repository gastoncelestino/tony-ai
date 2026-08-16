"""Tests for converting runtime executions into Kernel evidence."""

from kernel.runtime_evidence import execution_result_to_evidence
from kernel.runtime_executor import RuntimeExecutionResult
from kernel.schemas import EvidenceType


def test_execution_result_becomes_command_evidence():
    result = RuntimeExecutionResult(
        command=("pytest", "-q"),
        exit_code=0,
        stdout="2 passed\n",
        stderr="",
    )

    evidence = execution_result_to_evidence(result, claim="tests pass")

    assert evidence.type is EvidenceType.COMMAND
    assert evidence.claim == "tests pass"
    assert evidence.command == "pytest -q"
    assert evidence.exit_code == 0
    assert evidence.stdout == "2 passed\n"
    assert evidence.validate().value == "valid"


def test_execution_limits_are_preserved_as_evidence_metadata():
    result = RuntimeExecutionResult(
        command=("python", "-c", "..."),
        exit_code=None,
        timed_out=True,
        cpu_limited=False,
        memory_limited=False,
    )

    evidence = execution_result_to_evidence(result, claim="command completed")

    assert evidence.metadata == {
        "timed_out": True,
        "cpu_limited": False,
        "memory_limited": False,
    }
    assert evidence.exit_code is None
    assert evidence.validate().value == "invalid"
