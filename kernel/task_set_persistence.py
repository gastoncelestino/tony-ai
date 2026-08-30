"""Persistence adapter between the canonical TaskSet and TonyMem SDD state."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from .task_set import TaskSet


class TaskSetPersistenceError(ValueError):
    """Raised when persisted TaskSet data cannot be restored safely."""


class TaskSetPersistence:
    """Persist and restore TaskSet without making TonyMem an authority."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path

    @staticmethod
    def _store_module():
        path = Path(__file__).resolve().parent.parent / "local-memory" / "sdd_state.py"
        spec = importlib.util.spec_from_file_location("tony_sdd_state", path)
        if spec is None or spec.loader is None:
            raise TaskSetPersistenceError("TonyMem SDD store unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _validate_state(state: dict[str, Any]) -> TaskSet:
        try:
            tasks = state["tasks"]
            completed = state["completed"]
            if not isinstance(tasks, list) or not isinstance(completed, list):
                raise TypeError("tasks/completed must be lists")
            normalized_tasks = []
            for task in tasks:
                if not isinstance(task, dict):
                    raise TypeError("each task must be an object")
                normalized = dict(task)
                for field in ("dependencies", "files"):
                    value = normalized.get(field, ())
                    if not isinstance(value, (list, tuple)):
                        raise TypeError(f"{field} must be a list or tuple")
                    normalized[field] = tuple(value)
                normalized_tasks.append(normalized)
            task_set = TaskSet(tuple(normalized_tasks), tuple(completed))
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskSetPersistenceError(f"Invalid persisted TaskSet: {exc}") from exc
        return task_set

    def save(
        self,
        *,
        project_id: str,
        session_id: str,
        change_id: str,
        phase: str,
        status: str,
        task_set: TaskSet,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        module = self._store_module()
        try:
            return module.record_sdd_state(
                project_id=project_id,
                session_id=session_id,
                change_id=change_id,
                phase=phase,
                status=status,
                tasks=list(task_set.tasks),
                completed=list(task_set.completed),
                expected_version=expected_version,
                db_path=self.db_path,
            )
        except Exception as exc:
            raise TaskSetPersistenceError(f"Failed to persist TaskSet: {exc}") from exc

    def load(self, *, project_id: str, session_id: str) -> tuple[TaskSet, dict[str, Any]] | None:
        module = self._store_module()
        try:
            state = module.get_sdd_state(project_id, session_id, self.db_path)
        except Exception as exc:
            raise TaskSetPersistenceError(f"Failed to read persisted TaskSet: {exc}") from exc
        if state is None:
            return None
        return self._validate_state(state), state

    def load_for_context(
        self, *, project_id: str, session_id: str
    ) -> tuple[TaskSet, dict[str, Any]] | None:
        """Load session state, falling back to the project's active SDD state.

        OpenCode may issue a Task execution from a session different from the
        session that created the current SDD/TaskSet state. The workflow state
        is project-scoped for execution authorization, while session_id is
        still used as the preferred exact lookup and correlation key.
        """
        exact = self.load(project_id=project_id, session_id=session_id)
        if exact is not None:
            return exact

        module = self._store_module()
        try:
            conn = module.connect(self.db_path)
            try:
                module.init_sdd_state(conn)
                row = conn.execute(
                    "SELECT project_id, session_id, change_id, phase, status, tasks_json, "
                    "completed_json, version, updated_at "
                    "FROM sdd_state WHERE project_id=? "
                    "AND status NOT IN ('completed', 'archived', 'cancelled') "
                    "ORDER BY updated_at DESC, version DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
            finally:
                conn.close()

            if row is None:
                return None

            state = module._row_to_state(row)
        except Exception as exc:
            raise TaskSetPersistenceError(f"Failed to read active project TaskSet: {exc}") from exc

        return self._validate_state(state), state
