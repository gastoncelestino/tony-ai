"""Convert bounded runtime execution results into Kernel evidence."""
from __future__ import annotations

from .runtime_executor import RuntimeExecutionResult
from .schemas import Evidence, EvidenceType


def execution_result_to_evidence(
    result: RuntimeExecutionResult,
    *,
    claim: str,
) -> Evidence:
    """Represent one runtime execution as auditable command evidence."""
    return Evidence(
        type=EvidenceType.COMMAND,
        claim=claim,
        command=" ".join(result.command),
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        metadata={
            "timed_out": result.timed_out,
            "cpu_limited": result.cpu_limited,
            "memory_limited": result.memory_limited,
        },
    )


__all__ = ["execution_result_to_evidence"]
