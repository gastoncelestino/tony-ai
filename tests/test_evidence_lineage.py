from kernel.evidence_lineage import EvidenceLineageError, validate_evidence_refs
from kernel.schemas import Phase, TaskStatus
from kernel.task_graph import TaskNode, TaskStateGraph


def _graph() -> TaskStateGraph:
    return TaskStateGraph().add(
        TaskNode(
            task_id="task-1",
            description="test",
            phase=Phase.APPLY,
            status=TaskStatus.IN_PROGRESS,
            evidence_refs=("evidence:a", "evidence:b"),
        )
    )


def test_validate_evidence_refs_accepts_refs_attached_to_task():
    assert validate_evidence_refs(_graph(), "task-1", ["evidence:b", "evidence:a", "evidence:a"]) == (
        "evidence:b",
        "evidence:a",
    )


def test_validate_evidence_refs_rejects_unknown_ref():
    try:
        validate_evidence_refs(_graph(), "task-1", ["evidence:missing"])
    except EvidenceLineageError as exc:
        assert "not attached" in str(exc)
    else:
        raise AssertionError("expected EvidenceLineageError")


def test_validate_evidence_refs_rejects_unknown_task():
    try:
        validate_evidence_refs(_graph(), "missing", ["evidence:a"])
    except EvidenceLineageError as exc:
        assert "Unknown task" in str(exc)
    else:
        raise AssertionError("expected EvidenceLineageError")
