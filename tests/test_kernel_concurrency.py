from __future__ import annotations

import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kernel import persistence
from kernel.orchestrator_integration import KernelOrchestrator
from kernel.persistence import load_orchestrator, save_orchestrator, update_orchestrator


def _concurrent_task_worker(state_path: str, task_id: str, ready: multiprocessing.synchronize.Event, start: multiprocessing.synchronize.Event) -> None:
    ready.set()
    start.wait(timeout=30)
    update_orchestrator(
        lambda orch: orch.add_task(task_id, f"description for {task_id}", "explore"),
        path=state_path,
    )


class TestKernelConcurrency(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_multiprocess_updates_are_not_lost(self) -> None:
        state_path = self.tmp_path / "kernel-state.json"
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
            self.assertTrue(all(event.wait(timeout=30) for event in ready_events))
            start.set()
            for process in processes:
                process.join(timeout=30)
                self.assertEqual(process.exitcode, 0)
        finally:
            start.set()
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
        final = load_orchestrator(str(state_path))
        self.assertEqual(set(final.task_ledger.tasks), {f"task-{i}" for i in range(worker_count)})
        self.assertEqual(final.change_state.change_id, "concurrent-change")

    def test_corrupt_state_falls_back_to_fresh_state(self) -> None:
        for content in ("", "{\"change_state\":", json.dumps({"change_state": {}})):
            with self.subTest(content=content):
                state_path = self.tmp_path / f"corrupt-{len(content)}.json"
                state_path.write_text(content, encoding="utf-8")
                loaded = load_orchestrator(str(state_path))
                self.assertEqual(loaded.change_state.change_id, "default")
                self.assertEqual(loaded.change_state.current_phase.value, "explore")
                self.assertEqual(loaded.task_ledger.tasks, {})

    def test_orphaned_temporary_file_does_not_replace_valid_state(self) -> None:
        state_path = self.tmp_path / "kernel-state.json"
        save_orchestrator(KernelOrchestrator("stable-change", "test-project"), str(state_path))
        (self.tmp_path / "kernel-state.json.tmp").write_text("truncated", encoding="utf-8")
        loaded = load_orchestrator(str(state_path))
        self.assertEqual(loaded.change_state.change_id, "stable-change")
        self.assertTrue((self.tmp_path / "kernel-state.json.tmp").exists())

    def test_failed_write_keeps_previous_state(self) -> None:
        state_path = self.tmp_path / "kernel-state.json"
        save_orchestrator(KernelOrchestrator("before-failure", "test-project"), str(state_path))

        def fail_dump(*_args, **_kwargs):
            raise OSError("simulated interrupted write")

        with mock.patch.object(persistence.json, "dump", fail_dump):
            with self.assertRaisesRegex(OSError, "simulated interrupted write"):
                save_orchestrator(KernelOrchestrator("after-failure", "test-project"), str(state_path))

        loaded = load_orchestrator(str(state_path))
        self.assertEqual(loaded.change_state.change_id, "before-failure")

    def test_separate_explicit_state_paths_isolate_changes(self) -> None:
        path_a = self.tmp_path / "change-a" / "kernel-state.json"
        path_b = self.tmp_path / "change-b" / "kernel-state.json"
        save_orchestrator(KernelOrchestrator("change-a", "project"), str(path_a))
        save_orchestrator(KernelOrchestrator("change-b", "project"), str(path_b))
        self.assertEqual(load_orchestrator(str(path_a)).change_state.change_id, "change-a")
        self.assertEqual(load_orchestrator(str(path_b)).change_state.change_id, "change-b")


if __name__ == "__main__":
    unittest.main()
