"""
Tony Kernel — Task Ledger

Manages tasks, their dependencies, status, and evidence.
Implements "No task declared complete without evidence" rule.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Tuple, List

from .schemas import (
    Task,
    TaskStatus,
    TaskLedger,
    Phase,
    TaskStatus as TaskStatusEnum,
    Evidence,
    datetime,
)


# Re-export the TaskLedger from schemas (it's already defined there)
# This module provides additional helper functions

def create_task_ledger() -> 'TaskLedger':
    """Create an empty task ledger."""
    from .schemas import TaskLedger
    return TaskLedger(tasks={})


def create_task(
    task_id: str,
    description: str,
    phase: str,
    dependencies: Tuple[str, ...] = (),
    files: Tuple[str, ...] = (),
) -> 'Task':
    """Create a new task."""
    from .schemas import Task, TaskStatus, Phase
    return Task(
        id=task_id,
        description=description,
        phase=Phase(description.lower()) if description.lower() in [p.value for p in __import__('kernel.schemas', fromlist=['Phase']).schemas.Phase.__members__.values()] else Phase.TASKS,
        status=TaskStatus.PENDING,
        dependencies=dependencies,
        files=files,
    )