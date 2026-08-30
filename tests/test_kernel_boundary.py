from kernel.boundary import resolve_boundary


def task(task_id, dependencies=(), phase="explore"):
    return {
        "id": task_id,
        "description": task_id,
        "phase": phase,
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


def test_boundary_authorizes_requested_task_by_id():
    result = resolve_boundary(
        {
            "phase": "explore",
            "status": "pending",
            "tasks": [
                {"id": "explore-architecture", "description": "Inspect architecture", "phase": "explore", "dependencies": []},
                {"id": "analyze", "description": "Analyze flow", "phase": "explore", "dependencies": ["explore-architecture"]},
            ],
            "completed": [],
            "requested_description": "explore-architecture",
        }
    )

    assert result["allowed"] is True
    assert result["execution_order"]["task_id"] == "explore-architecture"


def test_boundary_blocks_requested_task_until_dependencies_complete():
    result = resolve_boundary(
        {
            "phase": "explore",
            "status": "pending",
            "tasks": [
                {"id": "explore", "description": "Explore", "phase": "explore", "dependencies": []},
                {"id": "analyze", "description": "Analyze", "phase": "explore", "dependencies": ["explore"]},
            ],
            "completed": [],
            "requested_description": "analyze",
        }
    )

    assert result["allowed"] is False
    assert "not ready" in result["reason"]


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


def test_boundary_blocks_when_no_task_is_ready_in_current_phase():
    result = resolve_boundary(
        {
            "phase": "explore",
            "status": "pending",
            "tasks": [task("A", phase="execute")],
            "completed": [],
        }
    )

    assert result["allowed"] is False
    assert result["decision"] == "blocked"
    assert result["execution_order"] is None


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
