from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

from kernel import persistence
from kernel.orchestrator_integration import KernelOrchestrator
from kernel.persistence import load_orchestrator, save_orchestrator, update_orchestrator


def _concurrent_task_worker(
    state_path: str,
    task_id: str,
    ready: multiprocessing.synchronize.Event,
    start: multiprocessing.synchronize.Event,
) -> None:
    """Run one transaction in a fresh process.

    The worker intentionally waits until all processes have loaded their
    execution context. The actual load happens inside update_orchestrator,
    under the sidecar lock, so each mutation observes the previous commit.
    """
    ready.set()
    start.wait(timeout=30)
    update_orchestrator(
        lambda orch: orch.add_task(task_id, f"description for {task_id}", "explore"),
        path=state_path,
    )


@pytest.mark.concurrency
def test_multiprocess_updates_are_not_lost(tmp_path: Path) -> None:
    """Every concurrent transaction must survive the load-modify-save race."""
    state_path = tmp_path / "kernel-state.json"
    save_orchestrator(KernelOrchestrator("concurrent-change", "test-project"), str(state_path))

    worker_count = 16
    context = multiprocessing.get_context("spawn")
    ready_events = [context.Event() for _ in range(worker_count)]
    start = context.Event()
    processes = [
        context.Process(
            target=_concurrent_task_worker,
            args=(str(state_path), f"task-{index}", ready_events[index], start),
        )
        for index in range(worker_count)
    ]

    for process in processes:
        process.start()

    try:
        assert all(event.wait(timeout=30) for event in ready_events)
        start.set()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
    finally:
        start.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    final = load_orchestrator(str(state_path))
    assert set(final.task_ledger.tasks) == {f"task-{i}" for i in range(worker_count)}
    assert final.change_state.change_id == "concurrent-change"


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{\"change_state\":",
        json.dumps({"change_state": {}}),
    ],
)
@pytest.mark.concurrency
def test_corrupt_state_falls_back_to_fresh_state(tmp_path: Path, content: str) -> None:
    state_path = tmp_path / "kernel-state.json"
    state_path.write_text(content, encoding="utf-8")

    loaded = load_orchestrator(str(state_path))

    assert loaded.change_state.change_id == "default"
    assert loaded.change_state.current_phase.value == "explore"
    assert loaded.task_ledger.tasks == {}


@pytest.mark.concurrency
def test_orphaned_temporary_file_does_not_replace_valid_state(tmp_path: Path) -> None:
    state_path = tmp_path / "kernel-state.json"
    save_orchestrator(KernelOrchestrator("stable-change", "test-project"), str(state_path))
    (tmp_path / "kernel-state.json.tmp").write_text("truncated", encoding="utf-8")

    loaded = load_orchestrator(str(state_path))

    assert loaded.change_state.change_id == "stable-change"
    assert (tmp_path / "kernel-state.json.tmp").exists()


@pytest.mark.concurrency
def test_failed_write_keeps_previous_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = tmp_path / "kernel-state.json"
    save_orchestrator(KernelOrchestrator("before-failure", "test-project"), str(state_path))

    def fail_dump(*_args, **_kwargs):
        raise OSError("simulated interrupted write")

    monkeypatch.setattr(persistence.json, "dump", fail_dump)
    with pytest.raises(OSError, match="simulated interrupted write"):
        save_orchestrator(KernelOrchestrator("after-failure", "test-project"), str(state_path))

    loaded = load_orchestrator(str(state_path))
    assert loaded.change_state.change_id == "before-failure"


@pytest.mark.concurrency
def test_separate_explicit_state_paths_isolate_changes(tmp_path: Path) -> None:
    path_a = tmp_path / "change-a" / "kernel-state.json"
    path_b = tmp_path / "change-b" / "kernel-state.json"

    save_orchestrator(KernelOrchestrator("change-a", "project"), str(path_a))
    save_orchestrator(KernelOrchestrator("change-b", "project"), str(path_b))

    assert load_orchestrator(str(path_a)).change_state.change_id == "change-a"
    assert load_orchestrator(str(path_b)).change_state.change_id == "change-b"
