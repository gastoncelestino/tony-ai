"""
Tony Kernel — Evidence Ledger

Tracks claims and their supporting evidence. Implements "No Evidence → No Progress" rule.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib

from .schemas import (
    Evidence,
    EvidenceType,
    EvidenceStatus,
    Claim,
    ClaimStatus,
    ExecutionRecord,
    Phase,
)


@dataclass
class EvidenceLedger:
    """
    Tracks claims and their evidence. Enforces "No Evidence → No Progress".
    """
    claims: dict[str, 'Claim'] = field(default_factory=dict)
    execution_records: list['ExecutionRecord'] = field(default_factory=list)

    def add_claim(self, claim: 'Claim') -> None:
        self.claims[claim.id] = claim

    def get_claim(self, claim_id: str) -> Optional['Claim']:
        return self.claims.get(claim_id)

    def add_execution_record(self, record: 'ExecutionRecord') -> None:
        self.execution_records.append(record)

    def get_claims_for_phase(self, phase: Phase) -> list['Claim']:
        # Claims are not directly tied to phase in this simple model
        # In practice, would filter by phase metadata
        return list(self.claims.values())

    def evaluate_claim(self, claim_id: str) -> 'Claim':
        claim = self.claims.get(claim_id)
        if not claim:
            raise KeyError(f"Claim {claim_id} not found")
        # Create new claim with evaluated status (immutable)
        from .schemas import Claim, ClaimStatus
        evaluated = Claim(
            id=claim.id,
            description=claim.description,
            evidence=claim.evidence,
            status=claim.evaluate(),
            required=claim.required,
            metadata=claim.metadata,
        )
        return type(self)._replace_claim(self, claim_id, evaluated)

    def _replace_claim(self, claim_id: str, new_claim: 'Claim') -> 'Claim':
        # For immutability, we'd need to rebuild the ledger
        # This is a mutable version for now
        self.claims[claim_id] = claim
        return claim

    def has_evidence_for_claim(self, claim_id: str) -> bool:
        claim = self.claims.get(claim_id)
        if not claim:
            return False
        return claim.evaluate() == 'supported'

    def get_unsupported_claims(self) -> list['Claim']:
        return [c for c in self.claims.values() if c.evaluate() != 'supported']

    def get_required_unsupported(self) -> list['Claim']:
        return [c for c in self.claims.values() if c.required and c.evaluate() != 'supported']

    def record_execution(self, command: str, args: tuple = (), exit_code: int = 0,
                         stdout: str = "", stderr: str = "", duration_ms: int = 0,
                         working_dir: str = None, env: dict = None, claim: str = "") -> 'ExecutionRecord':
        from .schemas import ExecutionRecord
        record = ExecutionRecord(
            command=command,
            args=args,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            working_dir=working_dir,
            env={} if env is None else env,
        )
        self.execution_records.append(record)
        return record

    def record_evidence(self, claim_id: str, evidence_type: str, claim: str,
                        exit_code: int = None, stdout: str = "", stderr: str = "",
                        file_path: str = None, file_hash: str = None,
                        metadata: dict = None) -> None:
        from .schemas import Evidence, EvidenceType, EvidenceStatus
        # Map string to EvidenceType
        type_map = {
            "test": "test",
            "build": "build",
            "lint": "lint",
            "command": "command",
            "git_diff": "git_diff",
            "file_exists": "file_exists",
            "file_content": "file_content",
            "manual": "manual",
        }
        ev_type = getattr(__import__('kernel.schemas', fromlist=['EvidenceType']).schemas, 'EvidenceType', None)
        if ev_type:
            ev_type = getattr(ev_type, evidence_type.upper(), None)
        else:
            # Fallback
            class ET:
                TEST = "test"; BUILD = "build"; LINT = "lint"
                COMMAND = "command"; GIT_DIFF = "git_diff"
                FILE_EXISTS = "file_exists"; FILE_CONTENT = "file_content"; MANUAL = "manual"
            ev_type = getattr(ET, evidence_type.upper(), None)

        evidence = Evidence(
            type=evidence_type,
            claim=claim,
            exit_code=exit_code,
            stdout=stdout[:10000] if len(stdout) > 10000 else stdout,  # truncate
            stderr=stderr[:5000] if len(stderr) > 5000 else stderr,
            file_path=None,
            metadata={},
        )
        # This is a mutable ledger for simplicity
        if claim_id in self.claims:
            claim_obj = self.claims[claim_id]
            new_evidence = list(claim.evidence) + [type('Evidence', (), {
                'type': evidence_type, 'claim': claim, 'exit_code': exit_code,
                'stdout': stdout[:10000], 'stderr': stderr[:5000]
            })]
            # Update claim (mutable for now)
            pass

    def has_evidence_for(self, claim_id: str) -> bool:
        claim = self.claims.get(claim_id)
        if not claim:
            return False
        return any(e.validate() == 'valid' for e in claim.evidence)

    def all_required_supported(self) -> bool:
        for claim in self.claims.values():
            if claim.required and claim.evaluate() != 'supported':
                return False
        return True