import sqlite3

import pytest

from kernel.task_set import TaskSet
from kernel.task_set_persistence import TaskSetPersistence, TaskSetPersistenceError


def make_task_set():
    return TaskSet(
        (
            {
                "id": "T1",
                "description": "prepare",
                "phase": "apply",
                "dependencies": (),
                "files": ("a.py",),
            },
            {
                "id": "T2",
                "description": "implement",
                "phase": "apply",
                "dependencies": ("T1",),
                "files": ("b.py",),
            },
        ),
        ("T1",),
    )


def test_task_set_round_trip(tmp_path):
    persistence = TaskSetPersistence(str(tmp_path / "memory.db"))
    original = make_task_set()

    persistence.save(
        project_id="p1",
        session_id="s1",
        change_id="c1",
        phase="apply",
        status="running",
        task_set=original,
    )

    loaded = persistence.load(project_id="p1", session_id="s1")
    assert loaded is not None
    restored, state = loaded
    assert restored.tasks == original.tasks
    assert restored.completed == original.completed
    assert state["version"] == 1


def test_persisted_invalid_dependency_is_rejected(tmp_path):
    db = tmp_path / "memory.db"
    persistence = TaskSetPersistence(str(db))
    persistence.save(
        project_id="p1",
        session_id="s1",
        change_id="c1",
        phase="apply",
        status="running",
        task_set=make_task_set(),
    )

    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE sdd_state SET tasks_json=? WHERE project_id=? AND session_id=?",
        ('[{"id":"T1","description":"prepare","phase":"apply","dependencies":[],"files":[]},'
         '{"id":"T2","description":"implement","phase":"apply","dependencies":["missing"],"files":[]}]',
         "p1", "s1"),
    )
    conn.commit()
    conn.close()

    with pytest.raises(TaskSetPersistenceError):
        persistence.load(project_id="p1", session_id="s1")


def test_missing_state_is_unavailable(tmp_path):
    persistence = TaskSetPersistence(str(tmp_path / "memory.db"))
    assert persistence.load(project_id="missing", session_id="missing") is None


def test_version_conflict_is_rejected(tmp_path):
    persistence = TaskSetPersistence(str(tmp_path / "memory.db"))
    task_set = make_task_set()
    persistence.save(
        project_id="p1",
        session_id="s1",
        change_id="c1",
        phase="apply",
        status="running",
        task_set=task_set,
    )

    with pytest.raises(TaskSetPersistenceError, match="version conflict"):
        persistence.save(
            project_id="p1",
            session_id="s1",
            change_id="c1",
            phase="apply",
            status="running",
            task_set=task_set,
            expected_version=0,
        )
