"""
Tony Kernel — Retry Budget

Tracks retry attempts per task/phase to prevent infinite loops.
Implements "Retry Budget" rule: max 3 attempts, then human required.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict
from enum import Enum

from .schemas import Phase


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
    attempts: Dict[str, list] = field(default_factory=dict)  # key: "phase:task_id"
    
    def get_key(self, phase: str, task_id: Optional[str] = None) -> str:
        return f"{phase}:{task_id or 'phase'}"
    
    def get_attempts(self, phase: str, task_id: Optional[str] = None) -> list:
        key = self.get_key(phase, task_id)
        return self.attempts.get(key, [])
    
    def record_attempt(self, phase: str, task_id: Optional[str], success: bool, 
                       error: Optional[str] = None, evidence: dict = None) -> dict:
        key = self.get_key(phase, task_id)
        attempts = self.attempts.get(key, [])
        attempt_num = len(attempts) + 1
        
        record = {
            "attempt_number": attempt_num,
            "phase": phase,
            "task_id": task_id,
            "success": success,
            "error": None,
            "evidence": evidence or {},
            "timestamp": __import__('datetime').datetime.now().isoformat(),
        }
        
        if attempt_num > self.max_attempts:
            action = "human_required"
        elif attempt_num == 1:
            action = "implement"
        else:
            action = "targeted_fix"
        
        record["action"] = action
        
        if key not in self.attempts:
            self.attempts[key] = []
        self.attempts[key].append(record)
        
        return {
            "attempt": attempt_num,
            "action": action,
            "max_reached": attempt_num >= self.max_attempts,
            "next_action": "human_required" if attempt_num >= self.max_attempts else ("targeted_fix" if attempt_num > 1 else "implement"),
        }
    
    def get_status(self, phase: str, task_id: Optional[str] = None) -> dict:
        attempts = self.get_attempts(phase)
        attempt_num = len(attempts)
        
        return {
            "attempts_used": attempt_num,
            "max_attempts": self.max_attempts,
            "remaining": max(0, self.max_attempts - len(self.attempts.get(self.get_key(phase), []))),
            "exhausted": len(self.attempts.get(self.get_key(phase), [])) >= self.max_attempts,
            "next_action": "human_required" if len(self.attempts.get(key, [])) >= self.max_attempts else ("targeted_fix" if len(self.attempts.get(key, [])) > 0 else "implement"),
            "last_attempt": self.attempts.get(key, [])[-1] if self.attempts.get(key) else None,
        }
    
    def is_exhausted(self, phase: str, task_id: Optional[str] = None) -> bool:
        key = self.get_key(phase, task_id)
        return len(self.attempts.get(key, [])) >= self.max_attempts
    
    def get_next_action(self, phase: str, task_id: Optional[str] = None) -> str:
        key = self.get_key(phase, task_id)
        attempts = len(self.attempts.get(key, []))
        
        if attempts >= self.max_attempts:
            return "human_required"
        elif attempts == 0:
            return "implement"
        else:
            return "targeted_fix"
    
    def reset(self, phase: str, task_id: Optional[str] = None) -> None:
        key = self.get_key(phase, task_id)
        if key in self.attempts:
            del self.attempts[key]