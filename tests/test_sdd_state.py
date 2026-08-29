import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "local-memory" / "sdd_state.py"
_spec = importlib.util.spec_from_file_location("tony_sdd_state", MODULE_PATH)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

get_sdd_state = _module.get_sdd_state
record_sdd_state = _module.record_sdd_state


def test_sdd_state_is_separate_and_versioned(tmp_path):
    db = tmp_path / "memory.db"
    tasks = [
        {
            "id": "T1",
            "description": "Implement feature",
            "phase": "apply",
            "dependencies": [],
        }
    ]

    first = record_sdd_state(
        project_id="project-a",
        session_id="session-1",
        change_id="change-1",
        phase="apply",
        status="pending",
        tasks=tasks,
        completed=[],
        db_path=str(db),
    )

    assert first["version"] == 1
    assert first["tasks"] == tasks

    second = record_sdd_state(
        project_id="project-a",
        session_id="session-1",
        change_id="change-1",
        phase="apply",
        status="running",
        tasks=tasks,
        completed=["T1"],
        expected_version=1,
        db_path=str(db),
    )

    assert second["version"] == 2
    assert second["status"] == "running"
    assert second["completed"] == ["T1"]

    loaded = get_sdd_state("project-a", "session-1", str(db))
    assert loaded == second


def test_sdd_state_version_conflict_is_rejected(tmp_path):
    db = tmp_path / "memory.db"
    record_sdd_state(
        project_id="project-a",
        session_id="session-1",
        change_id="change-1",
        phase="apply",
        status="pending",
        tasks=[],
        completed=[],
        db_path=str(db),
    )

    with pytest.raises(ValueError, match="version conflict"):
        record_sdd_state(
            project_id="project-a",
            session_id="session-1",
            change_id="change-1",
            phase="apply",
            status="running",
            tasks=[],
            completed=[],
            expected_version=0,
            db_path=str(db),
        )


def test_missing_sdd_state_is_unavailable(tmp_path):
    db = tmp_path / "memory.db"
    assert get_sdd_state("project-a", "missing", str(db)) is None
