from kernel.judgment_evidence import prepare_judgment_record
from kernel.evidence_lineage import EvidenceLineageError
from kernel.schemas import Phase, TaskStatus
from kernel.task_graph import TaskNode, TaskStateGraph


def _graph() -> TaskStateGraph:
    return TaskStateGraph().add(
        TaskNode(
            task_id="task-1",
            description="judged task",
            phase=Phase.APPLY,
            status=TaskStatus.IN_PROGRESS,
            evidence_refs=("evidence:a", "evidence:b"),
        )
    )


def test_prepare_judgment_record_validates_and_normalizes_refs():
    prepared = prepare_judgment_record(
        _graph(),
        "task-1",
        {
            "execution_id": "jd-1",
            "task": "judged task",
            "final": "approve",
            "evidence_refs": ["evidence:b", "evidence:a", "evidence:a"],
        },
    )

    assert prepared["evidence_refs"] == ["evidence:b", "evidence:a"]


def test_prepare_judgment_record_rejects_unknown_refs():
    try:
        prepare_judgment_record(
            _graph(),
            "task-1",
            {"evidence_refs": ["evidence:missing"]},
        )
    except EvidenceLineageError as exc:
        assert "not attached" in str(exc)
    else:
        raise AssertionError("expected EvidenceLineageError")


def test_prepare_judgment_record_rejects_string_refs():
    try:
        prepare_judgment_record(
            _graph(),
            "task-1",
            {"evidence_refs": "evidence:a"},
        )
    except ValueError as exc:
        assert "sequence" in str(exc)
    else:
        raise AssertionError("expected ValueError")
