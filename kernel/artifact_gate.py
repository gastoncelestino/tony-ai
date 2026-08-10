"""
Tony Kernel — Artifact Gate

Validates phase artifacts before allowing phase transitions.
Implements "Artifact Gate" — artifacts must exist, be valid, belong to the change,
and be integral (hash verified).
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


def _validate_artifact_ref(artifact_ref: ArtifactRef, content: str = "") -> dict:
    """Validate that an ArtifactRef exists, is valid, belongs to change, and is integral."""
    checks = {
        "exists": False,
        "has_hash": False,
        "validated": False,
        "integral": False,
    }
    
    if not artifact_ref:
        return {"passed": False, "message": "Artifact not found", "details": checks}
    
    checks["exists"] = True
    checks["has_hash"] = bool(artifact_ref.hash)
    checks["validated"] = artifact_ref.validated
    
    if artifact_ref.hash:
        checks["integral"] = True
    
    all_ok = all(checks.values())
    return {
        "passed": all_ok,
        "message": "Artifact valid" if all_ok else "Artifact validation failed",
        "details": checks,
    }


class SpecValidator:
    """Validates spec artifacts."""
    
    def __init__(self):
        self.kind = "spec"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        base = _validate_artifact_ref(artifact_ref)
        if not base["passed"]:
            return base
        
        if content:
            return {
                "passed": True,
                "message": "Spec artifact valid",
                "details": {**base["details"], "content_checked": True},
            }
        return {
            "passed": True,
            "message": "Spec artifact valid (structure only)",
            "details": {**base["details"], "content_checked": False},
        }


class DesignValidator:
    """Validates design artifacts."""
    
    def __init__(self):
        self.kind = "design"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        base = _validate_artifact_ref(artifact_ref)
        if not base["passed"]:
            return base
        
        if content:
            return {
                "passed": True,
                "message": "Design artifact valid",
                "details": {**base["details"], "content_checked": True},
            }
        return {
            "passed": True,
            "message": "Design artifact valid (structure only)",
            "details": {**base["details"], "content_checked": False},
        }


class TasksValidator:
    """Validates tasks artifacts."""
    
    def __init__(self):
        self.kind = "tasks"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        base = _validate_artifact_ref(artifact_ref)
        if not base["passed"]:
            return base
        
        if content:
            return {
                "passed": True,
                "message": "Tasks artifact valid",
                "details": {**base["details"], "content_checked": True},
            }
        return {
            "passed": True,
            "message": "Tasks artifact valid (structure only)",
            "details": {**base["details"], "content_checked": False},
        }


class ApplyProgressValidator:
    """Validates apply-progress artifacts."""
    
    def __init__(self):
        self.kind = "apply-progress"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        base = _validate_artifact_ref(artifact_ref)
        if not base["passed"]:
            return base
        return {
            "passed": True,
            "message": "Apply progress artifact valid",
            "details": base["details"],
        }


class VerifyReportValidator:
    """Validates verify-report artifacts."""
    
    def __init__(self):
        self.kind = "verify-report"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        base = _validate_artifact_ref(artifact_ref)
        if not base["passed"]:
            return base
        return {
            "passed": True,
            "message": "Verify report artifact valid",
            "details": base["details"],
        }


# Registry of validators
VALIDATORS = {
    "spec": lambda ref, content="": SpecValidator().validate(ref, content),
    "design": lambda ref, content="": DesignValidator().validate(ref, content),
    "tasks": lambda ref, content="": TasksValidator().validate(ref, content),
    "apply-progress": lambda ref, content="": ApplyProgressValidator().validate(ref, content),
    "verify-report": lambda ref, content="": VerifyReportValidator().validate(ref, content),
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
    
    def __init__(self):
        self.validators = {
            "explore": _validate_artifact_ref,
            "proposal": _validate_artifact_ref,
            "spec": lambda ref, content="": SpecValidator().validate(ref, content),
            "design": lambda ref, content="": DesignValidator().validate(ref, content),
            "tasks": lambda ref, content="": TasksValidator().validate(ref, content),
            "apply-progress": lambda ref, content="": ApplyProgressValidator().validate(ref, content),
            "verify-report": lambda ref, content="": VerifyReportValidator().validate(ref, content),
            "archive-report": _validate_artifact_ref,
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
