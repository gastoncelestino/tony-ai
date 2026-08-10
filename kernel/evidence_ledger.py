"""
Tony Kernel — Evidence Ledger

Tracks claims and their supporting evidence. Implements "No Evidence → No Progress" rule.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import hashlib

from .schemas import (
    Evidence,
    EvidenceType,
    EvidenceStatus,
    Claim,
    ClaimStatus,
    ExecutionRecord,
    Phase,
    Task,
    TaskStatus,
    TaskLedger,
)


@dataclass
class EvidenceLedger:
    """
    Tracks claims and their evidence. Implements "No Evidence → No Progress" rule.
    """
    claims: dict[str, 'Claim'] = field(default_factory=dict)
    execution_records: list = field(default_factory=list)

    def add_claim(self, claim: 'Claim') -> None:
        self.claims[claim.id] = claim

    def get_claim(self, claim_id: str) -> Optional['Claim']:
        return self.claims.get(claim_id)

    def add_execution_record(self, record: 'ExecutionRecord') -> None:
        self.execution_records.append(record)

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

    def get_unsupported_claims(self) -> list:
        return [c for c in self.claims.values() if c.evaluate() != 'supported']

    def get_required_unsupported(self) -> list:
        return [c for c in self.claims.values() if c.required and c.evaluate() != 'supported']