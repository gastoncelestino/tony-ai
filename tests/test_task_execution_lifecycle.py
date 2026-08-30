from kernel.state import KernelState
from kernel.task_set import TaskSet
from kernel.task_set_persistence import TaskSetPersistence


def make_task_set():
    return TaskSet(
        (
            {
                "id": "A",
                "description": "first",
                "phase": "explore",
                "dependencies": (),
            },
            {
                "id": "B",
                "description": "second",
                "phase": "explore",
                "dependencies": ("A",),
            },
        )
    )


def test_completed_task_unlocks_dependent_after_persistence(tmp_path):
    persistence = TaskSetPersistence(str(tmp_path / "memory.db"))
    task_set = make_task_set()

    persistence.save(
        project_id="p1",
        session_id="s1",
        change_id="c1",
        phase="explore",
        status="running",
        task_set=task_set,
    )

    loaded = persistence.load(project_id="p1", session_id="s1")
    assert loaded is not None
    loaded_tasks, state_data = loaded

    state = KernelState(state_data["phase"], state_data["status"]).select_next_task(loaded_tasks).start_task()
    completed_state, completed_tasks = state.complete_current_task(loaded_tasks, [{"kind": "test", "value": "ok"}])

    persistence.save(
        project_id="p1",
        session_id="s1",
        change_id="c1",
        phase=completed_state.current_phase,
        status=completed_state.current_status,
        task_set=completed_tasks,
        expected_version=state_data["version"],
    )

    reloaded = persistence.load(project_id="p1", session_id="s1")
    assert reloaded is not None
    persisted_tasks, persisted_state = reloaded
    assert persisted_tasks.completed == ("A",)
    assert persisted_tasks.ready_tasks()[0]["id"] == "B"
    assert persisted_state["version"] == 2

    next_state = KernelState(persisted_state["phase"], persisted_state["status"]).select_next_task(persisted_tasks).start_task()
    assert next_state.get_next_task()["id"] == "B"
