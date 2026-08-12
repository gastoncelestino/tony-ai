"""
Tests for Tony Kernel — Integration tests
stdlib-only (unittest) — no pytest dependency

Tests end-to-end integration between state machine, phase gate,
artifact gate, evidence ledger, and retry budget.
"""
from __future__ import annotations
import os
import sys
import unittest
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from kernel.schemas import (
    Phase,
    PhaseStatus,
    PhaseState,
    ChangeState,
    ArtifactRef,
    Evidence,
    EvidenceType,
    EvidenceStatus,
    ALLOWED_TRANSITIONS,
    REQUIRED_ARTIFACTS_FOR_TRANSITION,
)
from kernel.state_machine import (
    PhaseController,
    create_initial_state,
    InvalidTransitionError,
    MissingArtifactsError,
)
from kernel.phase_gate import PhaseGate, PhaseGateConfig
from kernel.artifact_gate import ArtifactGate
from kernel.evidence_ledger import EvidenceLedger
from kernel.retry_budget import RetryBudget
from kernel.orchestrator_integration import (
    KernelOrchestrator,
    create_kernel_orchestrator,
    OrchestrationDecision,
)


class TestIntegrationTransitions(unittest.TestCase):
    """Integration tests for phase transitions."""

    def test_spec_to_design_allowed(self):
        """spec → design is allowed after completing spec with valid artifact."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        
        result = orch.can_start_phase("explore")
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)
        orch.record_delegation("explore", "sub-agent")
        orch.record_phase_completion("explore", [
            {"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "abc123", "validated": True}
        ])
        
        result = orch.can_start_phase("propose")
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)
        orch.record_delegation("propose", "sub-agent")
        orch.record_phase_completion("propose", [
            {"kind": "proposal", "path": "sdd/test/proposal", "store": "tonymem", "hash": "def456", "validated": True}
        ])
        
        result = orch.can_start_phase("spec")
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)
        orch.record_delegation("spec", "sub-agent")
        orch.record_phase_completion("spec", [
            {"kind": "spec", "path": "sdd/test/spec", "store": "tonymem", "hash": "ghi789", "validated": True}
        ])
        
        result = orch.can_start_phase("design")
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)

    def test_spec_to_apply_denied(self):
        """spec → apply is denied (skipping design, tasks)."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        
        orch.record_delegation("explore", "sub-agent")
        orch.record_phase_completion("explore", [
            {"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "h1", "validated": True}
        ])
        orch.record_delegation("propose", "sub-agent")
        orch.record_phase_completion("propose", [
            {"kind": "proposal", "path": "sdd/test/proposal", "store": "tonymem", "hash": "h2", "validated": True}
        ])
        orch.record_delegation("spec", "sub-agent")
        orch.record_phase_completion("spec", [
            {"kind": "spec", "path": "sdd/test/spec", "store": "tonymem", "hash": "h3", "validated": True}
        ])
        
        result = orch.can_start_phase("apply")
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_INVALID_TRANSITION)

    def test_explore_to_spec_denied(self):
        """explore → spec is denied (skipping propose)."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        
        result = orch.can_start_phase("spec")
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_INVALID_TRANSITION)

    def test_full_sdd_chain(self):
        """Test full SDD chain: explore → propose → spec → design → tasks → apply."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        
        phases = ["explore", "propose", "spec", "design", "tasks", "apply"]
        artifact_map = {
            "explore": [{"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "h1", "validated": True}],
            "propose": [{"kind": "proposal", "path": "sdd/test/proposal", "store": "tonymem", "hash": "h2", "validated": True}],
            "spec": [{"kind": "spec", "path": "sdd/test/spec", "store": "tonymem", "hash": "h3", "validated": True}],
            "design": [{"kind": "design", "path": "sdd/test/design", "store": "tonymem", "hash": "h4", "validated": True}],
            "tasks": [{"kind": "tasks", "path": "sdd/test/tasks", "store": "tonymem", "hash": "h5", "validated": True}],
            "apply": [{"kind": "apply-progress", "path": "sdd/test/apply", "store": "tonymem", "hash": "h6", "validated": True}],
        }
        
        for phase in phases:
            result = orch.can_start_phase(phase)
            self.assertEqual(result.decision, OrchestrationDecision.PROCEED, f"Failed at phase {phase}: {result.reason}")
            orch.record_delegation(phase, "sub-agent")
            orch.record_phase_completion(phase, artifact_map[phase])


class TestIntegrationEvidence(unittest.TestCase):
    """Integration tests for evidence requirements."""

    def test_complete_task_requires_valid_evidence(self):
        """complete_task must reject invalid evidence."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        
        orch.add_task("t1", "Test task", "apply")
        orch.start_task("t1")
        
        result = orch.complete_task("t1", [])
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED)

    def test_complete_task_accepts_valid_command_evidence(self):
        """complete_task accepts valid command evidence (exit_code=0)."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        
        orch.add_task("t1", "Test task", "apply")
        orch.start_task("t1")
        
        evidence = Evidence(
            type=EvidenceType.COMMAND,
            claim="Tests pass",
            command="pytest",
            exit_code=0,
            stdout="passed",
        )
        result = orch.complete_task("t1", [evidence])
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)

    def test_complete_task_rejects_failed_command_evidence(self):
        """complete_task rejects evidence with non-zero exit code."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        
        orch.add_task("t1", "Test task", "apply")
        orch.start_task("t1")
        
        evidence = Evidence(
            type=EvidenceType.COMMAND,
            claim="Tests pass",
            command="pytest",
            exit_code=1,
            stdout="failed",
        )
        result = orch.complete_task("t1", [evidence])
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED)

    def test_record_phase_completion_accepts_no_evidence(self):
        """record_phase_completion still succeeds with no evidence at all
        (evidence is optional, not mandatory, per phase completion)."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        result = orch.record_phase_completion("explore", [
            {"kind": "explore", "path": "sdd/x/explore", "store": "tonymem", "hash": "abc123", "validated": True},
        ])
        self.assertEqual(result.decision, OrchestrationDecision.PHASE_COMPLETE)
        self.assertEqual(result.metadata.get("evidence_count"), 0)

    def test_record_phase_completion_accepts_valid_evidence(self):
        """record_phase_completion accepts well-formed evidence and reports
        how many items were validated."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        evidence = Evidence(
            type=EvidenceType.COMMAND,
            claim="Kernel tests pass",
            command="python3 -m unittest",
            exit_code=0,
            stdout="OK",
        )
        result = orch.record_phase_completion(
            "explore",
            [{"kind": "explore", "path": "sdd/x/explore", "store": "tonymem", "hash": "abc123", "validated": True}],
            [evidence],
        )
        self.assertEqual(result.decision, OrchestrationDecision.PHASE_COMPLETE)
        self.assertEqual(result.metadata.get("evidence_count"), 1)

    def test_record_phase_completion_rejects_fabricated_evidence(self):
        """record_phase_completion rejects evidence that fails validation
        (e.g. a claimed command with no exit_code) instead of silently
        discarding it and completing the phase anyway."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        fake_evidence = {"type": "command", "claim": "trust me, tests pass"}
        result = orch.record_phase_completion(
            "explore",
            [{"kind": "explore", "path": "sdd/x/explore", "store": "tonymem", "hash": "abc123", "validated": True}],
            [fake_evidence],
        )
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED)
        # And the phase state must NOT have advanced.
        status = orch.get_status()
        self.assertEqual(status["current_phase"], "explore")

    def test_record_phase_completion_rejects_failed_evidence(self):
        """A command evidence item with a non-zero exit_code is invalid,
        even at phase-completion level, not just at task-completion level."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        evidence = Evidence(
            type=EvidenceType.COMMAND,
            claim="Tests pass",
            command="pytest",
            exit_code=1,
            stdout="failed",
        )
        result = orch.record_phase_completion(
            "explore",
            [{"kind": "explore", "path": "sdd/x/explore", "store": "tonymem", "hash": "abc123", "validated": True}],
            [evidence],
        )
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED)


class TestIntegrationRetryBudget(unittest.TestCase):
    """Integration tests for retry budget."""

    def test_retry_budget_exhausted_blocks_phase(self):
        """When retry budget is exhausted, phase is blocked."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        
        orch.record_delegation("explore", "sub-agent")
        orch.record_phase_completion("explore", [
            {"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "h1", "validated": True}
        ])
        orch.record_delegation("propose", "sub-agent")
        orch.record_phase_completion("propose", [
            {"kind": "proposal", "path": "sdd/test/proposal", "store": "tonymem", "hash": "h2", "validated": True}
        ])
        orch.record_delegation("spec", "sub-agent")
        orch.record_phase_completion("spec", [
            {"kind": "spec", "path": "sdd/test/spec", "store": "tonymem", "hash": "h3", "validated": True}
        ])
        orch.record_delegation("design", "sub-agent")
        orch.record_phase_completion("design", [
            {"kind": "design", "path": "sdd/test/design", "store": "tonymem", "hash": "h4", "validated": True}
        ])
        orch.record_delegation("tasks", "sub-agent")
        orch.record_phase_completion("tasks", [
            {"kind": "tasks", "path": "sdd/test/tasks", "store": "tonymem", "hash": "h5", "validated": True}
        ])
        
        for _ in range(3):
            orch.retry_budget.record_attempt("apply", None, False, error="failed")
        
        result = orch.can_start_phase("apply")
        self.assertEqual(result.decision, OrchestrationDecision.HUMAN_REQUIRED)

    def test_retry_budget_three_attempts(self):
        """Test retry budget allows 3 attempts then blocks."""
        retry = RetryBudget()
        
        self.assertEqual(retry.get_next_action("apply"), "implement")
        retry.record_attempt("apply", None, False)
        self.assertEqual(retry.get_next_action("apply"), "targeted_fix")
        retry.record_attempt("apply", None, False)
        self.assertEqual(retry.get_next_action("apply"), "targeted_fix")
        retry.record_attempt("apply", None, False)
        self.assertEqual(retry.get_next_action("apply"), "human_required")
        self.assertTrue(retry.is_exhausted("apply"))


class TestIntegrationArtifactGate(unittest.TestCase):
    """Integration tests for artifact gate."""

    def test_missing_artifact_blocks_transition(self):
        """Missing artifact blocks phase transition."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        orch.record_delegation("explore", "sub-agent")
        orch.record_phase_completion("explore", [])
        
        result = orch.can_start_phase("propose")
        self.assertEqual(result.decision, OrchestrationDecision.BLOCK_MISSING_ARTIFACTS)

    def test_valid_artifact_allows_transition(self):
        """Valid artifact allows phase transition."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        orch.record_delegation("explore", "sub-agent")
        orch.record_phase_completion("explore", [
            {"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "abc123", "validated": True}
        ])
        
        result = orch.can_start_phase("propose")
        self.assertEqual(result.decision, OrchestrationDecision.PROCEED)


class TestIntegrationChecksum(unittest.TestCase):
    """Integration tests for phase checksum verification."""

    def test_verify_phase_checksum_after_completion(self):
        """verify_phase_checksum returns valid after recording."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        orch.record_delegation("explore", "sub-agent")
        orch.record_phase_completion("explore", [
            {"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "explore_hash", "validated": True}
        ])
        
        result = orch.verify_phase_checksum("explore", [
            {"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "explore_hash", "validated": True}
        ])
        self.assertEqual(result["status"], "valid")

    def test_verify_phase_checksum_detects_modification(self):
        """verify_phase_checksum detects modified artifacts."""
        orch = create_kernel_orchestrator("test-change", "test-project")
        orch.record_delegation("explore", "sub-agent")
        orch.record_phase_completion("explore", [
            {"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "explore_hash", "validated": True}
        ])
        
        result = orch.verify_phase_checksum("explore", [
            {"kind": "explore", "path": "sdd/test/explore", "store": "tonymem", "hash": "modified_hash", "validated": True}
        ])
        self.assertEqual(result["status"], "modified")


if __name__ == "__main__":
    unittest.main()
