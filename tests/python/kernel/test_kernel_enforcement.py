"""
Tony Kernel — enforcement contract tests.

These model the fail-closed contract the plugin + MCP server enforce on the
SDD flow, at the kernel boundary:

- every SDD delegation requires a kernel ALLOW (never implicit)
- kernel unavailable / corrupt state ⇒ delegation blocked, never allowed
- missing phase gate ⇒ blocked
- completion without kernel state ⇒ next phase blocked
- apply scope violation ⇒ blocked
- modified spec ⇒ blocks advancing (and archive)

Stdlib-only unittest.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kernel.artifact_store import disk_artifact_store, disk_artifact_hasher
from kernel.orchestrator_integration import create_kernel_orchestrator, OrchestrationDecision


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def tonymem_artifact(kind: str) -> dict:
    return {"kind": kind, "path": f"sdd/enf/{kind}", "store": "tonymem", "hash": "h-" + kind, "validated": True}


class TestEveryDelegationRequiresKernel(unittest.TestCase):

    def test_fresh_kernel_allows_only_explore(self):
        """A fresh kernel permits exactly one delegation (explore). Any other
        phase requires prior completion recorded in kernel state."""
        orch = create_kernel_orchestrator("c", "p")
        for phase in ["explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"]:
            result = orch.can_start_phase(phase)
            self.assertEqual(
                result.decision == OrchestrationDecision.PROCEED,
                phase == "explore",
                f"phase {phase} should{' ' if phase=='explore' else ' NOT '}be natively allowed",
            )

    def test_full_chain_requires_sequential_kernel_allows(self):
        """The whole SDD chain only advances because the kernel ALLOWs each
        phase in order — a delegation is never implicitly granted."""
        orch = create_kernel_orchestrator("c", "p")
        phases = ["explore", "propose", "spec", "design", "tasks", "apply", "verify"]
        kinds = {"explore": "explore", "propose": "proposal", "spec": "spec",
                 "design": "design", "tasks": "tasks", "apply": "apply-progress",
                 "verify": "verify-report"}
        for phase in phases:
            result = orch.can_start_phase(phase)
            self.assertEqual(result.decision, OrchestrationDecision.PROCEED,
                             f"kernel must allow {phase} after recording predecessors")
            orch.record_phase_completion(phase, [tonymem_artifact(kinds[phase])])
        result = orch.can_start_phase("archive")
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)

    def test_missing_phase_gate_blocks(self):
        """Delegating a phase the gate does not allow is blocked."""
        orch = create_kernel_orchestrator("c", "p")
        result = orch.can_start_phase("spec")
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_INVALID_TRANSITION)
        self.assertFalse(result.allowed if hasattr(result, "allowed") else False)

    def test_completion_without_kernel_state_blocks_next_phase(self):
        """An agent claiming 'propose done' with no kernel record of explore
        completion must be blocked — kernel state is the source of truth."""
        orch = create_kernel_orchestrator("c", "p")
        result = orch.can_start_phase("propose")
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_PHASE_INCOMPLETE)

    def test_kernel_unavailable_blocks_delegation(self):
        """Corrupt kernel state cannot confirm progress ⇒ a non-initial
        delegation is blocked (fail closed), never allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            state_dir.mkdir()
            (state_dir / "kernel-state.json").write_text("{ definitely not valid json !!!")
            env = dict(os.environ)
            env["TONY_KERNEL_STATE_DIR"] = str(state_dir)
            proc = subprocess.run(
                [sys.executable, "-m", "kernel.cli", "can_start_phase", "apply"],
                cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(out["decision"], "block_invalid_transition")
            self.assertFalse(out["allowed"])


class TestScopeGuard(unittest.TestCase):

    def test_apply_scope_violation_blocks_verify(self):
        orch = create_kernel_orchestrator("c", "p")
        diff = (
            "diff --git a/src/hack.js b/src/hack.js\n"
            "--- a/src/hack.js\n"
            "+++ b/src/hack.js\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        result = orch.check_scope(diff, ("kernel/*.py",))
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_SCOPE_VIOLATION)
        self.assertIn("src/hack.js", result.scope_violations)

        ok = orch.check_scope(diff, ("src/*",))
        self.assertEqual(ok.decision, OrchestrationDecision.PROCEED)


class TestModifiedSpecBlocksAdvance(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = disk_artifact_store(str(self.root))
        self.hasher = disk_artifact_hasher(str(self.root))
        self.orch = create_kernel_orchestrator("c", "p",
                                               artifact_store=self.store,
                                               artifact_hasher=self.hasher)

    def _write(self, rel: str, text: str) -> str:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return sha256_of(text)

    def _record_spec(self) -> dict:
        rel = "openspec/spec.md"
        h = self._write(rel, "spec v1\n")
        ref = {"kind": "spec", "path": rel, "store": "openspec", "hash": h, "validated": True}
        self.orch.record_phase_completion("explore", [tonymem_artifact("explore")])
        self.orch.record_phase_completion("propose", [tonymem_artifact("proposal")])
        result = self.orch.record_phase_completion("spec", [ref])
        self.assertEqual(result.decision, OrchestrationDecision.PHASE_COMPLETE)
        return ref

    def test_verify_uses_disk_truth_not_reported_hash(self):
        """After tampering, verification reads the file from disk — even when
        the caller reports the original (stale) hash, it must be MODIFIED."""
        ref = self._record_spec()
        (self.root / "openspec" / "spec.md").write_text("spec v2 - tampered\n")
        res = self.orch.verify_phase_checksum("spec", [ref])
        self.assertEqual(res["status"], "modified")

    def test_modified_spec_blocks_advance(self):
        ref = self._record_spec()
        (self.root / "openspec" / "spec.md").write_text("spec v2 - tampered\n")
        # a tampered required artifact blocks the next phase (and thus archive)
        result = self.orch.can_start_phase("design")
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_MISSING_ARTIFACTS)

    def test_intact_spec_advances(self):
        ref = self._record_spec()
        res = self.orch.verify_phase_checksum("spec", [ref])
        self.assertEqual(res["status"], "valid")
        result = self.orch.can_start_phase("design")
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)


if __name__ == "__main__":
    unittest.main()
