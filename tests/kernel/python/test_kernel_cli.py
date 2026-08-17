"""
Tony Kernel CLI — integration tests through the real subprocess path.

These exercise kernel/cli.py exactly as the tony-kernel plugin does: spawning
`python3 -m kernel.cli` from the repo root, one invocation per command, with
kernel state persisted to an isolated state file between calls.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

def run_cli(state_dir: Path, *args, expect_ok: bool = True):
    env = dict(os.environ)
    env["TONY_KERNEL_STATE_DIR"] = str(state_dir)
    proc = subprocess.run(
        [sys.executable, "-m", "kernel.cli", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if expect_ok:
        assert proc.returncode == 0, f"CLI failed ({proc.returncode}): {proc.stderr}"
        return json.loads(proc.stdout)
    return proc


def tonymem_artifact(kind: str) -> dict:
    return {"kind": kind, "path": f"sdd/cli-test/{kind}", "store": "tonymem", "hash": "h-" + kind, "validated": True}


class TestKernelCli(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name) / "kernel-state.json"

    def test_health_ok(self):
        out = run_cli(self.state_dir, "health")
        self.assertEqual(out["status"], "ok")

    def test_fresh_state_allows_explore(self):
        out = run_cli(self.state_dir, "can_start_phase", "explore")
        self.assertEqual(out["decision"], "proceed")
        self.assertTrue(out["allowed"])

    def test_skip_transition_denied(self):
        out = run_cli(self.state_dir, "can_start_phase", "apply")
        self.assertEqual(out["decision"], "block_invalid_transition")
        self.assertFalse(out["allowed"])

    def test_state_persists_between_calls(self):
        run_cli(self.state_dir, "record_phase_completion", "explore", json.dumps([tonymem_artifact("explore")]))
        out = run_cli(self.state_dir, "can_start_phase", "propose")
        self.assertEqual(out["decision"], "proceed")
        self.assertTrue(out["allowed"])

    def test_evidence_mandatory_for_task_completion(self):
        out = run_cli(self.state_dir, "complete_task", "t1", "[]")
        self.assertEqual(out["decision"], "block_evidence_required")
        self.assertFalse(out["allowed"])

    def test_add_start_complete_task_lifecycle(self):
        run_cli(self.state_dir, "add_task", "t1", "Implement feature", "apply")
        out = run_cli(self.state_dir, "start_task", "t1")
        self.assertEqual(out["ok"], True)
        out = run_cli(self.state_dir, "complete_task", "t1", json.dumps([
            {"type": "test", "claim": "tests pass", "command": "pytest", "exit_code": 0}
        ]))
        self.assertEqual(out["decision"], "proceed")

    def test_verify_phase_checksum(self):
        run_cli(self.state_dir, "record_phase_completion", "explore", json.dumps([tonymem_artifact("explore")]))
        out = run_cli(self.state_dir, "verify_phase_checksum", "explore", json.dumps([tonymem_artifact("explore")]))
        self.assertEqual(out["status"], "valid")

    def test_get_status_shape(self):
        out = run_cli(self.state_dir, "status")
        self.assertIn("current_phase", out)
        self.assertIn("phase_summary", out)
        self.assertIn("task_summary", out)

    def test_reset_returns_to_fresh(self):
        run_cli(self.state_dir, "record_phase_completion", "explore", json.dumps([tonymem_artifact("explore")]))
        run_cli(self.state_dir, "reset")
        out = run_cli(self.state_dir, "can_start_phase", "explore")
        self.assertEqual(out["decision"], "proceed")

    def test_unknown_command_fails(self):
        proc = run_cli(self.state_dir, "no_such_command", expect_ok=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Unknown command", proc.stderr)

    def test_record_delegation_then_progress(self):
        run_cli(self.state_dir, "record_delegation", "explore", "sdd-explore")
        run_cli(self.state_dir, "record_phase_completion", "explore", json.dumps([tonymem_artifact("explore")]))
        out = run_cli(self.state_dir, "can_start_phase", "propose")
        self.assertTrue(out["allowed"])


if __name__ == "__main__":
    unittest.main()
