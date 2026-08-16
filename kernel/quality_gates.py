"""Declarative quality-gate policy for Kernel arbitration.

This module defines the policy layer only. It does not execute tests, security
checks, or judgment agents; it determines which gates apply and how their
reported outcomes affect a deterministic decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Mapping, Sequence


class QualityGateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MISSING = "missing"
    SKIPPED = "skipped"


class QualityGateDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class GateCondition:
    """Conditions controlling whether a gate applies to a task/change."""

    paths: tuple[str, ...] = ()
    risk: str | None = None

    def matches(self, *, paths: Sequence[str] = (), risk: str | None = None) -> bool:
        """Return whether this condition applies to the supplied context."""
        if self.paths and not any(
            fnmatch(path, pattern) for path in paths for pattern in self.paths
        ):
            return False
        if self.risk is not None and self.risk != risk:
            return False
        return True


@dataclass(frozen=True, slots=True)
class QualityGate:
    """One declarative quality gate."""

    name: str
    required: bool = True
    when: GateCondition = field(default_factory=GateCondition)

    def applies(self, *, paths: Sequence[str] = (), risk: str | None = None) -> bool:
        return self.when.matches(paths=paths, risk=risk)


@dataclass(frozen=True, slots=True)
class QualityGatePolicy:
    """Immutable collection of gates evaluated by the Kernel."""

    gates: tuple[QualityGate, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "QualityGatePolicy":
        """Build a policy from a YAML/JSON-compatible mapping."""
        raw_gates = data.get("gates", ())
        if not isinstance(raw_gates, Sequence) or isinstance(raw_gates, (str, bytes)):
            raise ValueError("gates must be a sequence")

        gates: list[QualityGate] = []
        names: set[str] = set()
        for raw in raw_gates:
            if not isinstance(raw, Mapping):
                raise ValueError("each gate must be a mapping")
            name = raw.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("gate name must be a non-empty string")
            if name in names:
                raise ValueError(f"duplicate gate name: {name}")
            names.add(name)

            required = raw.get("required", True)
            if not isinstance(required, bool):
                raise ValueError(f"gate {name}: required must be boolean")

            raw_when = raw.get("when", {})
            if raw_when is None:
                raw_when = {}
            if not isinstance(raw_when, Mapping):
                raise ValueError(f"gate {name}: when must be a mapping")

            raw_paths = raw_when.get("paths", ())
            if isinstance(raw_paths, str):
                raw_paths = (raw_paths,)
            if not isinstance(raw_paths, Sequence):
                raise ValueError(f"gate {name}: when.paths must be a sequence")
            paths = tuple(raw_paths)
            if not all(isinstance(path, str) and path for path in paths):
                raise ValueError(f"gate {name}: when.paths must contain strings")

            risk = raw_when.get("risk")
            if risk is not None and (not isinstance(risk, str) or not risk):
                raise ValueError(f"gate {name}: when.risk must be a non-empty string")

            gates.append(
                QualityGate(
                    name=name,
                    required=required,
                    when=GateCondition(paths=paths, risk=risk),
                )
            )
        return cls(gates=tuple(gates))

    def applicable(
        self, *, paths: Sequence[str] = (), risk: str | None = None
    ) -> tuple[QualityGate, ...]:
        """Return applicable gates in declaration order."""
        return tuple(gate for gate in self.gates if gate.applies(paths=paths, risk=risk))

    def evaluate(
        self,
        results: Mapping[str, QualityGateStatus | str],
        *,
        paths: Sequence[str] = (),
        risk: str | None = None,
    ) -> "QualityGateEvaluation":
        """Evaluate applicable gate results without executing any gate."""
        applicable = self.applicable(paths=paths, risk=risk)
        failures: list[str] = []
        missing: list[str] = []
        evaluated: list[tuple[str, QualityGateStatus]] = []

        for gate in applicable:
            raw_status = results.get(gate.name)
            if raw_status is None:
                status = QualityGateStatus.MISSING
            else:
                try:
                    status = QualityGateStatus(raw_status)
                except ValueError as exc:
                    raise ValueError(
                        f"unknown result for gate {gate.name}: {raw_status}"
                    ) from exc
            evaluated.append((gate.name, status))
            if gate.required and status is QualityGateStatus.MISSING:
                missing.append(gate.name)
            elif gate.required and status is QualityGateStatus.FAIL:
                failures.append(gate.name)

        decision = QualityGateDecision.BLOCK if failures or missing else QualityGateDecision.ALLOW
        return QualityGateEvaluation(
            decision=decision,
            applicable=tuple(name for name, _ in evaluated),
            failures=tuple(failures),
            missing=tuple(missing),
            results=tuple(evaluated),
        )


@dataclass(frozen=True, slots=True)
class QualityGateEvaluation:
    """Deterministic policy result returned to the Kernel."""

    decision: QualityGateDecision
    applicable: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    results: tuple[tuple[str, QualityGateStatus], ...] = ()


__all__ = [
    "GateCondition",
    "QualityGate",
    "QualityGateDecision",
    "QualityGateEvaluation",
    "QualityGatePolicy",
    "QualityGateStatus",
]
