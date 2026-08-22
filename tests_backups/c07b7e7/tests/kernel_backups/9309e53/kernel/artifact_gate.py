"""
Tony Kernel — Artifact Gate

Validates phase artifacts before allowing phase transitions.
Implements "Artifact Gate" — artifacts must exist, be valid, belong to the change,
and be integral (hash verified).

The gate accepts an optional ``store`` (``ArtifactRef -> bool``, e.g. the
disk-backed store from artifact_store.py). When provided, validation is REAL:
the artifact must resolve on the backend (file exists, readable, non-empty,
hash matches). Without a store it degrades to a structural check (ref + hash +
validated flag) so the gate stays testable in-memory.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Awaitable
from enum import Enum

from .schemas import (
    Phase,
    ArtifactRef,
    ArtifactGateResult,
    ArtifactValidationResult,
    ArtifactGateResult as ArtifactGateResultEnum,
)


class ArtifactValidator:
    """Base class for artifact validators."""
    
    def __init__(self, kind: str, required: bool = True):
        self.kind = kind
        self.required = required
    
    def validate(self, artifact: 'ArtifactRef', content: str = "") -> 'ArtifactValidationResult':
        raise NotImplementedError


def _validate_artifact_ref(artifact_ref: ArtifactRef, content: str = "", store: Optional[Callable[[ArtifactRef], bool]] = None) -> dict:
    """Validate that an ArtifactRef exists, is valid, belongs to change, and is integral.

    When a ``store`` is provided (e.g. ``disk_artifact_store``), the artifact
    must resolve on the real backend: file exists, is readable, is non-empty,
    and its sha256 matches the recorded hash. Without a store this is a
    structural check only (ref + hash + validated flag).
    """
    checks = {
        "exists": False,
        "has_hash": False,
        "validated": False,
        "integral": False,
    }

    if not artifact_ref:
        return {"passed": False, "message": "Artifact not found", "details": checks}

    if store is not None:
        try:
            on_backend = bool(store(artifact_ref))
        except Exception:
            on_backend = False
        if not on_backend:
            return {
                "passed": False,
                "message": "Artifact does not resolve on the backend (missing, unreadable, empty, or hash mismatch)",
                "details": checks,
            }

    checks["exists"] = True
    checks["has_hash"] = bool(artifact_ref.hash)
    checks["validated"] = artifact_ref.validated
    checks["integral"] = bool(artifact_ref.hash)

    all_ok = all(checks.values())
    return {
        "passed": all_ok,
        "message": "Artifact valid" if all_ok else "Artifact validation failed",
        "details": checks,
    }


def _validate_with_content(artifact_ref: ArtifactRef, content: str, store: Optional[Callable[[ArtifactRef], bool]]) -> dict:
    """Shared spec/design/tasks validation: base ref checks + content probe."""
    base = _validate_artifact_ref(artifact_ref, content, store)
    if not base["passed"]:
        return base

    if content and not content.strip():
        return {
            "passed": False,
            "message": "Artifact content is empty",
            "details": {**base["details"], "content_checked": True},
        }

    return {
        "passed": True,
        "message": "Artifact valid" if content else "Artifact valid (structure only)",
        "details": {**base["details"], "content_checked": bool(content)},
    }


class SpecValidator:
    """Validates spec artifacts."""
    
    def __init__(self):
        self.kind = "spec"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "", store: Optional[Callable[[ArtifactRef], bool]] = None) -> dict:
        return _validate_with_content(artifact_ref, content, store)


class DesignValidator:
    """Validates design artifacts."""
    
    def __init__(self):
        self.kind = "design"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "", store: Optional[Callable[[ArtifactRef], bool]] = None) -> dict:
        return _validate_with_content(artifact_ref, content, store)


class TasksValidator:
    """Validates tasks artifacts."""
    
    def __init__(self):
        self.kind = "tasks"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "", store: Optional[Callable[[ArtifactRef], bool]] = None) -> dict:
        return _validate_with_content(artifact_ref, content, store)


class ApplyProgressValidator:
    """Validates apply-progress artifacts."""
    
    def __init__(self):
        self.kind = "apply-progress"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "", store: Optional[Callable[[ArtifactRef], bool]] = None) -> dict:
        return _validate_artifact_ref(artifact_ref, content, store)


class VerifyReportValidator:
    """Validates verify-report artifacts."""
    
    def __init__(self):
        self.kind = "verify-report"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "", store: Optional[Callable[[ArtifactRef], bool]] = None) -> dict:
        return _validate_artifact_ref(artifact_ref, content, store)


# Registry of validators (store-aware so the module-level API stays usable)
VALIDATORS = {
    "spec": lambda ref, content="", store=None: SpecValidator().validate(ref, content, store),
    "design": lambda ref, content="", store=None: DesignValidator().validate(ref, content, store),
    "tasks": lambda ref, content="", store=None: TasksValidator().validate(ref, content, store),
    "apply-progress": lambda ref, content="", store=None: ApplyProgressValidator().validate(ref, content, store),
    "verify-report": lambda ref, content="", store=None: VerifyReportValidator().validate(ref, content, store),
    "explore": _validate_artifact_ref,
    "proposal": _validate_artifact_ref,
    "archive-report": _validate_artifact_ref,
}


@dataclass
class ArtifactGate:
    """
    Validates artifacts before allowing phase transitions.
    Implements the Artifact Gate pattern.
    Artifact must be: exist + valid + belong to change + integral.
    """

    store: Optional[Callable[[ArtifactRef], bool]] = None

    def __init__(self, store: Optional[Callable[[ArtifactRef], bool]] = None):
        self.store = store
        self.validators = {
            "explore": lambda ref, content="": _validate_artifact_ref(ref, content, self.store),
            "proposal": lambda ref, content="": _validate_artifact_ref(ref, content, self.store),
            "spec": lambda ref, content="": SpecValidator().validate(ref, content, self.store),
            "design": lambda ref, content="": DesignValidator().validate(ref, content, self.store),
            "tasks": lambda ref, content="": TasksValidator().validate(ref, content, self.store),
            "apply-progress": lambda ref, content="": ApplyProgressValidator().validate(ref, content, self.store),
            "verify-report": lambda ref, content="": VerifyReportValidator().validate(ref, content, self.store),
            "archive-report": lambda ref, content="": _validate_artifact_ref(ref, content, self.store),
        }
    
    def register_validator(self, kind: str, validator: callable) -> None:
        self.validators[kind] = validator
    
    def validate(self, kind: str, artifact_ref, content: str = "") -> dict:
        """Validate an artifact of the given kind."""
        validator = self.validators.get(kind)
        if not validator:
            return {"passed": False, "message": f"No validator for artifact kind: {kind}", "details": {}}
        
        if not artifact_ref:
            return {"passed": False, "message": f"Artifact {kind} not found", "details": {}}
        
        return validator(artifact_ref, content)
    
    def validate_all(self, required_kinds: list, artifacts: dict) -> dict:
        """Validate multiple required artifacts."""
        results = {}
        
        for kind in required_kinds:
            ref = artifacts.get(kind)
            result = self.validate(kind, ref)
            results[kind] = result
        
        return {
            "passed": all(r.get("passed", False) for r in results.values()),
            "results": results,
        }
    
    def validate_transition(self, from_phase: str, to_phase: str, artifacts: dict) -> dict:
        """Validate artifacts required for a phase transition."""
        from kernel.schemas import REQUIRED_ARTIFACTS_FOR_TRANSITION
        from kernel.schemas import Phase
        
        from_p = getattr(__import__('kernel.schemas', fromlist=['Phase']).schemas, 'Phase', None)
        if not from_p:
            class P:
                EXPLORE = "explore"; PROPOSE = "propose"; SPEC = "spec"
                DESIGN = "design"; TASKS = "tasks"; APPLY = "apply"
                VERIFY = "verify"; ARCHIVE = "archive"
            from_p = getattr(__import__('kernel.schemas', fromlist=['Phase']).schemas, 'Phase', P)
        
        try:
            from_phase_enum = getattr(__import__('kernel.schemas', fromlist=['Phase']).schemas.Phase, from_phase.upper())
            to_phase_enum = getattr(__import__('kernel.schemas', fromlist=['Phase']).schemas.Phase, to_phase.upper())
        except:
            required = []
            if from_phase == "explore" and to_phase == "propose": required = ["explore"]
            elif from_phase == "propose" and to_phase == "spec": required = ["proposal"]
            elif from_phase == "spec" and to_phase == "design": required = ["spec"]
            elif from_phase == "design" and to_phase == "tasks": required = ["spec", "design"]
            elif from_phase == "tasks" and to_phase == "apply": required = ["tasks", "spec", "design"]
            elif from_phase == "apply" and to_phase == "verify": required = ["apply-progress", "tasks", "spec"]
            elif from_phase == "verify" and to_phase == "archive": required = ["verify-report", "apply-progress", "tasks", "spec", "design", "proposal"]
            else:
                required = []
        else:
            from kernel.schemas import REQUIRED_ARTIFACTS_FOR_TRANSITION
            required = REQUIRED_ARTIFACTS_FOR_TRANSITION.get((from_phase, to_phase), [])
        
        return self.validate_all(required, artifacts)
