"""Tests for Kernel arbitration of declarative quality gates."""

from kernel import (
    QualityGateDecision,
    QualityGatePolicy,
    QualityGateStatus,
    TaskGraphKernelOrchestrator,
)


def _policy():
    return QualityGatePolicy.from_mapping(
        {
            "gates": [
                {"name": "tests", "required": True},
                {"name": "security", "required": True, "when": {"paths": ["auth/**"]}},
                {"name": "judgment", "required": True, "when": {"risk": "high"}},
            ]
        }
    )


def test_kernel_selects_only_applicable_quality_gates():
    kernel = TaskGraphKernelOrchestrator(
        "change-1", "test-project", quality_gate_policy=_policy()
    )
    evaluation = kernel.evaluate_quality_gates(
        {"tests": QualityGateStatus.PASS},
        paths=("src/app.py",),
        risk="low",
    )
    assert evaluation.decision is QualityGateDecision.ALLOW
    assert evaluation.applicable == ("tests",)


def test_kernel_blocks_when_required_applicable_gate_is_missing():
    kernel = TaskGraphKernelOrchestrator(
        "change-1", "test-project", quality_gate_policy=_policy()
    )
    evaluation = kernel.evaluate_quality_gates(
        {"tests": QualityGateStatus.PASS},
        paths=("auth/login.py",),
        risk="low",
    )
    assert evaluation.decision is QualityGateDecision.BLOCK
    assert evaluation.applicable == ("tests", "security")
    assert evaluation.missing == ("security",)


def test_kernel_applies_risk_gate_without_executing_it():
    kernel = TaskGraphKernelOrchestrator(
        "change-1", "test-project", quality_gate_policy=_policy()
    )
    evaluation = kernel.evaluate_quality_gates(
        {"tests": QualityGateStatus.PASS, "judgment": QualityGateStatus.PASS},
        paths=("src/app.py",),
        risk="high",
    )
    assert evaluation.decision is QualityGateDecision.ALLOW
    assert evaluation.applicable == ("tests", "judgment")
    assert evaluation.results == (
        ("tests", QualityGateStatus.PASS),
        ("judgment", QualityGateStatus.PASS),
    )


def test_kernel_blocks_required_failed_gate_but_ignores_optional_failure():
    policy = QualityGatePolicy.from_mapping(
        {
            "gates": [
                {"name": "tests", "required": True},
                {"name": "lint", "required": False},
            ]
        }
    )
    kernel = TaskGraphKernelOrchestrator(
        "change-1", "test-project", quality_gate_policy=policy
    )
    evaluation = kernel.evaluate_quality_gates(
        {"tests": QualityGateStatus.PASS, "lint": QualityGateStatus.FAIL}
    )
    assert evaluation.decision is QualityGateDecision.ALLOW
    assert evaluation.failures == ()
