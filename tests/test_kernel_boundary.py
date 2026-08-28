from kernel.boundary import resolve_boundary


def task(task_id, dependencies=()):
    return {
        "id": task_id,
        "description": task_id,
        "phase": "explore",
        "dependencies": dependencies,
    }


def test_boundary_selects_and_authorizes_first_ready_task():
    result = resolve_boundary(
        {
            "phase": "explore",
            "status": "pending",
            "tasks": [task("A"), task("B", ("A",))],
            "completed": [],
        }
    )

    assert result["allowed"] is True
    assert result["decision"] == "proceed"
    assert result["execution_order"]["task_id"] == "A"


def test_boundary_uses_completed_tasks_to_enable_successor():
    result = resolve_boundary(
        {
            "phase": "explore",
            "status": "pending",
            "tasks": [task("A"), task("B", ("A",))],
            "completed": ["A"],
        }
    )

    assert result["allowed"] is True
    assert result["execution_order"]["task_id"] == "B"


def test_boundary_blocks_when_no_task_is_ready():
    result = resolve_boundary(
        {
            "phase": "explore",
            "status": "pending",
            "tasks": [task("A"), task("B", ("A",))],
            "completed": [],
        }
    )

    assert result["allowed"] is True
    assert result["execution_order"]["task_id"] == "A"


def test_boundary_fails_closed_on_invalid_task_snapshot():
    result = resolve_boundary(
        {
            "phase": "explore",
            "status": "pending",
            "tasks": [{"id": "A", "dependencies": ("missing",)}],
            "completed": [],
        }
    )

    assert result["allowed"] is False
    assert result["decision"] == "blocked"
