"""Tests for declarative quality-gate policy evaluation."""

import pytest

from kernel.quality_gates import (
    QualityGateDecision,
    QualityGatePolicy,
    QualityGateStatus,
)


def test_policy_applies_unconditional_gate_and_required_result():
    policy = QualityGatePolicy.from_mapping(
        {"gates": [{"name": "tests", "required": True}]}
    )

    evaluation = policy.evaluate({"tests": "pass"})

    assert evaluation.decision is QualityGateDecision.ALLOW
    assert evaluation.applicable == ("tests",)
    assert evaluation.failures == ()
    assert evaluation.missing == ()


def test_path_condition_selects_security_gate():
    policy = QualityGatePolicy.from_mapping(
        {
            "gates": [
                {"name": "tests"},
                {
                    "name": "security",
                    "when": {"paths": ["auth/**", "**/crypto/**"]},
                },
            ]
        }
    )

    evaluation = policy.evaluate(
        {"tests": "pass", "security": "pass"}, paths=("auth/login.py",)
    )

    assert evaluation.applicable == ("tests", "security")
    assert evaluation.decision is QualityGateDecision.ALLOW


def test_risk_condition_does_not_apply_to_low_risk_change():
    policy = QualityGatePolicy.from_mapping(
        {"gates": [{"name": "judgment", "when": {"risk": "high"}}]}
    )

    evaluation = policy.evaluate({}, risk="low")

    assert evaluation.applicable == ()
    assert evaluation.decision is QualityGateDecision.ALLOW


def test_required_missing_gate_blocks():
    policy = QualityGatePolicy.from_mapping(
        {"gates": [{"name": "tests", "required": True}]}
    )

    evaluation = policy.evaluate({})

    assert evaluation.decision is QualityGateDecision.BLOCK
    assert evaluation.missing == ("tests",)


def test_optional_failed_gate_does_not_block():
    policy = QualityGatePolicy.from_mapping(
        {"gates": [{"name": "qa", "required": False}]}
    )

    evaluation = policy.evaluate({"qa": QualityGateStatus.FAIL})

    assert evaluation.decision is QualityGateDecision.ALLOW
    assert evaluation.failures == ()


def test_duplicate_gate_names_are_rejected():
    with pytest.raises(ValueError, match="duplicate gate name"):
        QualityGatePolicy.from_mapping(
            {"gates": [{"name": "tests"}, {"name": "tests"}]}
        )


def test_invalid_gate_result_is_rejected():
    policy = QualityGatePolicy.from_mapping({"gates": [{"name": "tests"}]})

    with pytest.raises(ValueError, match="unknown result"):
        policy.evaluate({"tests": "unknown"})
