"""Tests for phase artifact checksum integrity."""
from __future__ import annotations

import unittest

from kernel.orchestrator_integration import create_kernel_orchestrator
from kernel.phase_checksum import PhaseChecksumRegistry
from kernel.schemas import ArtifactRef


class TestPhaseChecksum(unittest.TestCase):
    def _artifact(self, content: str) -> ArtifactRef:
        return ArtifactRef(
            kind="spec",
            path="openspec/spec.md",
            store="openspec",
        ).compute_hash(content)

    def test_recorded_artifact_verifies_unchanged(self):
        registry = PhaseChecksumRegistry()
        artifact = self._artifact("original spec")

        registry.record_phase("spec", [artifact], recorded_by="kernel")
        result = registry.verify_phase("spec", [artifact])

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["modified_artifacts"], [])
        self.assertEqual(result["missing_artifacts"], [])

    def test_modified_artifact_is_detected(self):
        registry = PhaseChecksumRegistry()
        original = self._artifact("original spec")
        modified = self._artifact("tampered spec")

        registry.record_phase("spec", [original], recorded_by="kernel")
        result = registry.verify_phase("spec", [modified])

        self.assertEqual(result["status"], "modified")
        self.assertEqual(result["modified_artifacts"], ["spec"])

    def test_missing_artifact_is_detected(self):
        registry = PhaseChecksumRegistry()
        artifact = self._artifact("original spec")

        registry.record_phase("spec", [artifact], recorded_by="kernel")
        result = registry.verify_phase("spec", [])

        self.assertEqual(result["status"], "modified")
        self.assertEqual(result["missing_artifacts"], ["spec"])

    def test_orchestrator_recomputes_hash_from_artifact_hasher(self):
        stored = self._artifact("original spec")
        current = self._artifact("current spec")

        def hasher(_artifact: ArtifactRef):
            return current.hash

        orchestrator = create_kernel_orchestrator(
            "checksum-test",
            "test-project",
            artifact_hasher=hasher,
        )
        orchestrator.checksum_registry.record_phase(
            "spec", [stored], recorded_by="kernel"
        )

        result = orchestrator.verify_phase_checksum("spec", [stored])

        self.assertEqual(result["status"], "modified")
        self.assertEqual(result["modified_artifacts"], ["spec"])


if __name__ == "__main__":
    unittest.main()
