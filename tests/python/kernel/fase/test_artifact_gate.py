"""Tests for Artifact Gate validation and fail-closed behavior."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.artifact_gate import ArtifactGate
from kernel.artifact_store import disk_artifact_store
from kernel.schemas import ArtifactRef


class TestArtifactGate(unittest.TestCase):
    def _artifact(self, content: str = "artifact") -> ArtifactRef:
        return ArtifactRef(
            kind="spec",
            path="openspec/spec.md",
            store="openspec",
            validated=True,
        ).compute_hash(content)

    def test_valid_artifact_passes(self):
        gate = ArtifactGate()

        result = gate.validate("spec", self._artifact(), "valid spec")

        self.assertTrue(result["passed"])
        self.assertEqual(result["message"], "Artifact valid")

    def test_missing_artifact_fails_closed(self):
        gate = ArtifactGate()

        result = gate.validate("spec", None)

        self.assertFalse(result["passed"])
        self.assertIn("not found", result["message"])

    def test_unvalidated_artifact_is_rejected(self):
        gate = ArtifactGate()
        artifact = ArtifactRef(
            kind="spec",
            path="openspec/spec.md",
            store="openspec",
            hash="abc",
            validated=False,
        )

        result = gate.validate("spec", artifact)

        self.assertFalse(result["passed"])
        self.assertFalse(result["details"]["validated"])

    def test_unknown_artifact_kind_fails_closed(self):
        gate = ArtifactGate()

        result = gate.validate("unknown", self._artifact())

        self.assertFalse(result["passed"])
        self.assertIn("No validator", result["message"])

    def test_backend_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "openspec" / "spec.md"
            path.parent.mkdir(parents=True)
            path.write_text("tampered", encoding="utf-8")

            gate = ArtifactGate(store=disk_artifact_store(tmp))
            artifact = self._artifact("original")
            result = gate.validate("spec", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("backend", result["message"])


if __name__ == "__main__":
    unittest.main()
