"""
Tony Kernel — Phase Checksum

Tracks checksums of phase artifacts to detect drift/tampering.
Prevents reward hacking where agents modify specs to match implementation.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum
import hashlib
import json

from .schemas import Phase, ArtifactRef


class ChecksumStatus(str, Enum):
    VALID = "valid"
    MODIFIED = "modified"
    MISSING = "missing"
    CORRUPTED = "corrupted"


@dataclass(frozen=True, slots=True)
class PhaseChecksum:
    """Checksum record for a phase's artifacts."""
    phase: str
    artifacts_hash: str  # Combined hash of all artifacts
    individual_hashes: Dict[str, str]  # kind -> hash
    recorded_at: datetime
    recorded_by: str  # agent or system that recorded it


@dataclass
class PhaseChecksumResult:
    status: str  # "valid", "modified", "missing", "corrupted"
    phase: str
    expected_hash: str
    actual_hash: Optional[str] = None
    modified_artifacts: List[str] = field(default_factory=list)
    missing_artifacts: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)


class PhaseChecksumRegistry:
    """
    Registry of phase checksums for drift detection.
    
    When a phase completes, we record the checksums of its artifacts.
    Later, we can verify that artifacts haven't been modified (drift detection).
    """
    
    def __init__(self):
        self.checksums: Dict[str, PhaseChecksum] = {}
        self.history: List[Dict] = []  # Audit trail
    
    def record_phase(self, phase: str, artifacts: List, recorded_by: str = "system") -> PhaseChecksum:
        """
        Record checksums for all artifacts in a phase.
        
        Args:
            phase: Phase name (e.g., "spec", "design", "tasks")
            artifacts: List of ArtifactRef objects
            recorded_by: Who recorded this (agent name or "system")
        
        Returns:
            PhaseChecksum with combined and individual hashes
        """
        individual_hashes = {}
        content_parts = []
        
        for art in artifacts:
            if art.hash:
                individual_hashes[art.kind] = art.hash
                content_parts.append(f"{art.kind}:{art.hash}")
        
        # Combined hash of all artifacts
        combined_content = "|".join(sorted(content_parts))
        combined_hash = hashlib.sha256(combined_content.encode()).hexdigest()
        
        checksum = PhaseChecksum(
            phase=phase,
            artifacts_hash=combined_hash,
            individual_hashes=individual_hashes,
            recorded_at=datetime.now(),
            recorded_by=recorded_by,
        )
        
        self.checksums[phase] = checksum
        
        # Record in history
        self.history.append({
            "action": "record",
            "phase": phase,
            "hash": combined_hash,
            "timestamp": datetime.now().isoformat(),
            "by": recorded_by,
        })
        
        return self.checksums[phase]
    
    def verify_phase(self, phase: str, current_artifacts: List) -> Dict:
        """
        Verify that phase artifacts haven't been modified since recording.
        
        Returns:
            Dict with status, modified artifacts, missing artifacts, etc.
        """
        if phase not in self.checksums:
            return {
                "status": "missing",
                "phase": phase,
                "message": f"No checksum recorded for phase {phase}",
                "modified_artifacts": [],
                "missing_artifacts": [],
            }
        
        recorded = self.checksums[phase]
        current_hashes = {}
        current_content = []
        
        for art in current_artifacts:
            if art.hash:
                current_hashes[art.kind] = art.hash
                current_content.append(f"{art.kind}:{art.hash}")
        
        # Compute current combined hash
        current_combined = hashlib.sha256("|".join(sorted(current_content)).encode()).hexdigest()
        
        # Check combined hash
        if current_combined != recorded.artifacts_hash:
            # Find which artifacts changed
            modified = []
            missing = []
            
            for kind, expected_hash in recorded.individual_hashes.items():
                if kind not in current_hashes:
                    missing.append(kind)
                elif current_hashes[kind] != expected_hash:
                    modified.append(kind)
            
            # Also check for new artifacts
            for kind in current_hashes:
                if kind not in recorded.individual_hashes:
                    # New artifact added - could be OK or suspicious
                    pass
            
            return {
                "status": "modified",
                "phase": phase,
                "expected_hash": recorded.artifacts_hash,
                "actual_hash": current_combined,
                "modified_artifacts": modified,
                "missing_artifacts": missing,
                "details": {
                    "recorded_at": recorded.recorded_at.isoformat(),
                    "recorded_by": recorded.recorded_by,
                }
            }
        
        return {
            "status": "valid",
            "phase": phase,
            "expected_hash": recorded.artifacts_hash,
            "actual_hash": current_combined,
            "modified_artifacts": [],
            "missing_artifacts": [],
        }
    
    def get_checksum(self, phase: str) -> Optional[Dict]:
        """Get stored checksum info for a phase."""
        if phase not in self.checksums:
            return None
        
        cs = self.checksums[phase]
        return {
            "phase": cs.phase,
            "hash": cs.artifacts_hash,
            "individual_hashes": cs.individual_hashes,
            "recorded_at": cs.recorded_at.isoformat(),
            "recorded_by": cs.recorded_by,
        }
    
    def list_phases(self) -> List[str]:
        return list(self.checksums.keys())
    
    def clear_phase(self, phase: str) -> bool:
        """Clear checksum for a phase (e.g., after legitimate re-planning)."""
        if phase in self.checksums:
            del self.checksums[phase]
            self.history.append({
                "action": "clear",
                "phase": phase,
                "timestamp": datetime.now().isoformat(),
            })
            return True
        return False
    
    def get_audit_trail(self) -> List[Dict]:
        """Get full audit trail of checksum operations."""
        return self.history.copy()


# Global registry instance
_global_registry = None

def get_global_registry() -> PhaseChecksumRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = PhaseChecksumRegistry()
    return _global_registry