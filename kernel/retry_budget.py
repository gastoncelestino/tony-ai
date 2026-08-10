"""
Tony Kernel — Retry Budget (Fixed Version)

Tracks retry attempts per task/phase to prevent infinite loops.
Implements "Retry Budget" rule: max 3 attempts, then human required.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum


class RetryAction(str, Enum):
    IMPLEMENT = "implement"
    TARGETED_FIX = "targeted_fix"
    HUMAN_REQUIRED = "human_required"


@dataclass
class AttemptRecord:
    """Record of a single attempt."""
    attempt_number: int
    action: str
    phase: str
    task_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    success: bool = False
    error: Optional[str] = None
    evidence: dict = field(default_factory=dict)


@dataclass
class RetryBudget:
    """
    Tracks retry attempts per task/phase.
    Max 3 attempts: implement → targeted fix → targeted fix → human required.
    """
    max_attempts: int = 3
    attempts: Dict[str, List[dict]] = field(default_factory=dict)
    
    def get_key(self, phase: str, task_id: Optional[str] = None) -> str:
        return f"{phase}:{task_id or 'phase'}"
    
    def get_attempts(self, phase: str, task_id: Optional[str] = None) -> list:
        key = self.get_key(phase, task_id)
        return self.attempts.get(key, [])
    
    def record_attempt(self, phase: str, task_id: Optional[str], success: bool, 
                       error: Optional[str] = None, evidence: dict = None) -> dict:
        key = f"{phase}:{task_id or 'phase'}"
        attempts = self.attempts.get(key, [])
        attempt_num = len(attempts) + 1
        
        record = {
            "attempt_number": len(self.attempts.get(key, [])) + 1,
            "phase": phase,
            "task_id": task_id,
            "success": success,
            "error": None,
            "evidence": evidence or {},
            "timestamp": __import__('datetime').datetime.now().isoformat(),
        }
        
        if key not in self.attempts:
            self.attempts[key] = []
        self.attempts[key].append(record)
        
        return {
            "attempt": len(self.attempts[key]),
            "action": "human_required" if len(self.attempts[key]) >= 3 else ("targeted_fix" if len(self.attempts[key]) > 1 else "implement"),
            "max_reached": len(self.attempts[key]) >= 3,
            "next_action": "human_required" if len(self.attempts[key]) >= 3 else ("targeted_fix" if len(self.attempts[key]) > 0 else "implement"),
        }
    
    def get_status(self, phase: str, task_id: Optional[str] = None) -> dict:
        key = f"{phase}:{task_id or 'phase'}"
        attempts = self.attempts.get(key, [])
        attempt_num = len(attempts)
        
        return {
            "attempts_used": len(self.attempts.get(key, [])),
            "max_attempts": 3,
            "remaining": max(0, 3 - len(self.attempts.get(key, []))),
            "exhausted": len(self.attempts.get(key, [])) >= 3,
            "next_action": "human_required" if len(self.attempts.get(key, [])) >= 3 else ("targeted_fix" if len(self.attempts[key]) > 0 else "implement"),
            "last_attempt": self.attempts.get(key, [])[-1] if self.attempts.get(key) else None,
        }
    
    def is_exhausted(self, phase: str, task_id: Optional[str] = None) -> bool:
        key = f"{phase}:{task_id or 'phase'}"
        return len(self.attempts.get(key, [])) >= 3
    
    def get_next_action(self, phase: str, task_id: Optional[str] = None) -> str:
        key = f"{phase}:{task_id or 'phase'}"
        attempts = len(self.attempts.get(key, []))
        
        if attempts >= 3:
            return "human_required"
        elif attempts == 0:
            return "implement"
        else:
            return "targeted_fix"
    
    def reset(self, phase: str, task_id: Optional[str] = None) -> None:
        key = f"{phase}:{task_id or 'phase'}"
        if key in self.attempts:
            del self.attempts[key]