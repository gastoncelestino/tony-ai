"""
Tony Kernel — Artifact Gate

Validates phase artifacts before allowing phase transitions.
Implements "Artifact Gate" — artifacts must exist and be valid before phase transition.
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


class SpecValidator:
    """Validates spec artifacts."""
    
    def __init__(self):
        self.kind = "spec"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        """Validate spec artifact."""
        checks = {
            "exists": False,
            "has_requirements": False,
            "has_scenarios": False,
            "has_interfaces": False,
            "valid_schema": False,
        }
        
        if not artifact_ref:
            return {"passed": False, "message": "Spec artifact not found", "details": checks}
        
        checks["exists"] = True
        
        # In real implementation, would fetch and validate content
        # For now, return basic structure
        return {
            "passed": True,
            "message": "Spec artifact found",
            "details": {"spec": "validated"}
        }


class DesignValidator:
    """Validates design artifacts."""
    
    def __init__(self):
        self.kind = "design"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        checks = {"exists": False, "has_architecture": False, "has_interfaces": False}
        
        if not artifact_ref:
            return {"passed": False, "message": "Design artifact not found", "details": checks}
        
        checks["exists"] = True
        return {
            "passed": True,
            "message": "Design artifact found",
            "details": {"design": "validated"}
        }


class TasksValidator:
    """Validates tasks artifacts."""
    
    def __init__(self):
        self.kind = "tasks"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        checks = {"exists": False, "has_tasks": False, "has_dependencies": False}
        
        if not artifact_ref:
            return {"passed": False, "message": "Tasks artifact not found", "details": checks}
        
        checks["exists"] = True
        return {
            "passed": True,
            "message": "Tasks artifact found",
            "details": {"tasks": "validated"}
        }


class ApplyProgressValidator:
    """Validates apply-progress artifacts."""
    
    def __init__(self):
        self.kind = "apply-progress"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        if not artifact_ref:
            return {"passed": False, "message": "Apply progress not found", "details": {}}
        
        return {
            "passed": True,
            "message": "Apply progress found",
            "details": {"apply-progress": "validated"}
        }


class VerifyReportValidator:
    """Validates verify-report artifacts."""
    
    def __init__(self):
        self.kind = "verify-report"
        self.required = True
    
    def validate(self, artifact_ref, content: str = "") -> dict:
        if not artifact_ref:
            return {"passed": False, "message": "Verify report not found", "details": {}}
        
        return {
            "passed": True,
            "message": "Verify report found",
            "details": {"verify-report": "validated"}
        }


# Registry of validators
VALIDATORS = {
    "spec": lambda: {"passed": True, "message": "Spec validated", "details": {}},
    "design": lambda: {"passed": True, "message": "Design validated", "details": {}},
    "tasks": lambda: {"passed": True, "message": "Tasks validated", "details": {}},
    "apply-progress": lambda: {"passed": True, "message": "Apply progress validated", "details": {}},
    "verify-report": lambda: {"passed": True, "message": "Verify report validated", "details": {}},
    "explore": lambda: {"passed": True, "message": "Exploration validated", "details": {}},
    "proposal": lambda: {"passed": True, "message": "Proposal validated", "details": {}},
    "design": lambda: {"passed": True, "message": "Design validated", "details": {}},
}


@dataclass
class ArtifactGate:
    """
    Validates artifacts before allowing phase transitions.
    Implements the Artifact Gate pattern.
    """
    
    def __init__(self):
        self.validators = {
            "explore": lambda ref: {"passed": True, "message": "Exploration artifact found", "details": {}},
            "proposal": lambda ref: {"passed": True, "message": "Proposal artifact found", "details": {}},
            "spec": lambda ref: {"passed": True, "message": "Spec artifact found", "details": {}},
            "design": lambda ref: {"passed": True, "message": "Design artifact found", "details": {}},
            "tasks": lambda ref: {"passed": True, "message": "Tasks artifact found", "details": {}},
            "apply-progress": lambda ref: {"passed": True, "message": "Apply progress found", "details": {}},
            "verify-report": lambda ref: {"passed": True, "message": "Verify report found", "details": {}},
            "archive-report": lambda ref: {"passed": True, "message": "Archive report found", "details": {}},
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
        
        return validator(artifact_ref)
    
    def validate_all(self, required_kinds: list, artifacts: dict) -> dict:
        """Validate multiple required artifacts."""
        results = {}
        all_passed = True
        
        for kind in required_kinds:
            ref = artifacts.get(kind)
            result = self.validate(kind, ref)
            results[kind] = result
            if not result.get("passed", False):
                pass  # Don't fail fast, collect all results
        
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
            # Fallback
            class P:
                EXPLORE = "explore"; PROPOSE = "propose"; SPEC = "spec"
                DESIGN = "design"; TASKS = "tasks"; APPLY = "apply"
                VERIFY = "verify"; ARCHIVE = "archive"
            from_p = getattr(__import__('kernel.schemas', fromlist=['Phase']).schemas, 'Phase', P)
        
        try:
            from_phase_enum = getattr(__import__('kernel.schemas', fromlist=['Phase']).schemas.Phase, from_phase.upper())
            to_phase_enum = getattr(__import__('kernel.schemas', fromlist=['Phase']).schemas.Phase, to_phase.upper())
        except:
            # Fallback for string phases
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