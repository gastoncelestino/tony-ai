"""
Tony Kernel — hardening regression tests.

Covers the bridge between the kernel engines (PhaseChecksumRegistry,
ArtifactGate, TaskLedger) and the real flow:

1. verify_phase_checksum routes through PhaseChecksumRegistry (valid /
   modified / missing), not a placeholder.
2. ArtifactGate validates against the real backend when a disk store is wired
   (exists, readable, non-empty, hash match), and tampering blocks the next
   phase transition — the recreated gate must keep the store.
3. TaskLedger.complete_task never marks a task COMPLETED without evidence.
4. create_task honors the phase parameter instead of guessing from description.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from kernel.artifact_store import disk_artifact_store
from kernel.artifact_gate import ArtifactGate
from kernel.orchestrator_integration import create_kernel_orchestrator, OrchestrationDecision
from kernel.schemas import ArtifactRef, Evidence, EvidenceType, Phase, Task, TaskLedger, TaskStatus


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class TestVerifyPhaseChecksumWiring(unittest.TestCase):
    """verify_phase_checksum must reach PhaseChecksumRegistry, not return True."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.orch = create_kernel_orchestrator("hc", "hp",
                                               artifact_store=disk_artifact_store(str(self.root)))

    def _explore_ref(self) -> dict:
        (self.root / "sdd").mkdir(exist_ok=True)
        (self.root / "sdd" / "explore.md").write_text("findings\n")
        return {
            "kind": "explore",
            "path": "sdd/explore.md",
            "store": "openspec",
            "hash": sha256_of("findings\n"),
            "validated": True,
        }

    def test_verify_returns_valid_after_completion(self):
        ref = self._explore_ref()
        self.orch.record_phase_completion("explore", [ref])
        res = self.orch.verify_phase_checksum("explore", [ref])
        self.assertEqual(res["status"], "valid")

    def test_verify_detects_modified_artifact(self):
        ref = self._explore_ref()
        self.orch.record_phase_completion("explore", [ref])
        tampered = dict(ref, hash=sha256_of("different\n"))
        res = self.orch.verify_phase_checksum("explore", [tampered])
        self.assertEqual(res["status"], "modified")

    def test_verify_missing_when_phase_never_recorded(self):
        res = self.orch.verify_phase_checksum("apply", [])
        self.assertEqual(res["status"], "missing")


class TestArtifactGateStore(unittest.TestCase):
    """ArtifactGate must verify the real backend when a disk store is wired."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = disk_artifact_store(str(self.root))

    def _write(self, rel: str, text: str) -> str:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return sha256_of(text)

    def test_gate_accepts_existing_file_with_matching_hash(self):
        rel = "openspec/changes/x/spec.md"
        h = self._write(rel, "spec content\n")
        ref = ArtifactRef(kind="spec", path=rel, store="openspec", hash=h, validated=True)
        res = ArtifactGate(store=self.store).validate("spec", ref)
        self.assertTrue(res["passed"], res)

    def test_gate_rejects_missing_file(self):
        ref = ArtifactRef(kind="spec", path="openspec/changes/x/spec.md",
                          store="openspec", hash="deadbeef", validated=True)
        res = ArtifactGate(store=self.store).validate("spec", ref)
        self.assertFalse(res["passed"])
        self.assertIn("backend", res["message"])

    def test_gate_rejects_hash_mismatch(self):
        rel = "openspec/changes/x/spec.md"
        self._write(rel, "real content\n")
        ref = ArtifactRef(kind="spec", path=rel, store="openspec",
                          hash=sha256_of("other content"), validated=True)
        self.assertFalse(ArtifactGate(store=self.store).validate("spec", ref)["passed"])

    def test_gate_rejects_empty_file(self):
        rel = "openspec/changes/x/spec.md"
        h = self._write(rel, "")
        ref = ArtifactRef(kind="spec", path=rel, store="openspec", hash=h, validated=True)
        self.assertFalse(ArtifactGate(store=self.store).validate("spec", ref)["passed"])

    def test_gate_without_store_falls_back_to_structural_check(self):
        ref = ArtifactRef(kind="spec", path="nowhere/spec.md", store="openspec",
                          hash="abc", validated=True)
        self.assertTrue(ArtifactGate().validate("spec", ref)["passed"])

    def test_tampering_blocks_next_phase_after_completion(self):
        """Regression: the gate recreated after record_phase_completion must keep
        the disk store, otherwise tampering is invisible to later checks."""
        (self.root / "sdd").mkdir(exist_ok=True)
        (self.root / "sdd" / "explore.md").write_text("findings\n")
        ref = {
            "kind": "explore",
            "path": "sdd/explore.md",
            "store": "openspec",
            "hash": sha256_of("findings\n"),
            "validated": True,
        }
        orch = create_kernel_orchestrator("c", "p", artifact_store=self.store)
        result = orch.record_phase_completion("explore", [ref])
        self.assertEqual(result.decision, OrchestrationDecision.PHASE_COMPLETE)

        result = orch.can_start_phase("propose")
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)

        (self.root / "sdd" / "explore.md").write_text("tampered\n")
        result = orch.can_start_phase("propose")
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_MISSING_ARTIFACTS)

    def test_record_completion_rejects_artifact_missing_on_disk(self):
        ref = {"kind": "explore", "path": "sdd/ghost.md", "store": "openspec",
               "hash": "abc", "validated": True}
        orch = create_kernel_orchestrator("c", "p", artifact_store=self.store)
        result = orch.record_phase_completion("explore", [ref])
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_ARTIFACT_INVALID)


class TestTaskLedgerEvidenceGuard(unittest.TestCase):
    """No evidence, no progress — enforced at the ledger level too."""

    def _ledger_with_in_progress(self) -> TaskLedger:
        ledger = TaskLedger().add_task(Task(id="t1", description="x", phase=Phase.APPLY))
        return ledger.start_task("t1")

    def test_ledger_does_not_complete_task_without_evidence(self):
        ledger = self._ledger_with_in_progress()
        ledger = ledger.complete_task("t1", ())
        self.assertEqual(ledger.get_task("t1").status, TaskStatus.IN_PROGRESS)

    def test_ledger_completes_task_with_evidence(self):
        ledger = self._ledger_with_in_progress()
        ev = Evidence(type=EvidenceType.COMMAND, claim="ok", command="pytest", exit_code=0)
        ledger = ledger.complete_task("t1", (ev,))
        self.assertEqual(ledger.get_task("t1").status, TaskStatus.COMPLETED)


class TestCreateTask(unittest.TestCase):
    """create_task must use the phase parameter, not guess from the description."""

    def test_phase_param_is_used(self):
        from kernel.task_ledger import create_task
        task = create_task("t1", "Implement feature", "apply")
        self.assertEqual(task.phase, Phase.APPLY)
        task2 = create_task("t2", "any description", "design")
        self.assertEqual(task2.phase, Phase.DESIGN)

    def test_orchestrator_add_task_preserves_phase(self):
        orch = create_kernel_orchestrator("c", "p")
        orch.add_task("t1", "Implement", "design")
        self.assertEqual(orch.task_ledger.get_task("t1").phase, Phase.DESIGN)


if __name__ == "__main__":
    unittest.main()
