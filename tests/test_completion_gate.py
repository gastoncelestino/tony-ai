"""Tests for the minimal completion evidence gate."""
from kernel.completion_gate import validate_completion


def test_completion_with_evidence_is_allowed():
    assert validate_completion([{"kind": "test", "value": "16 passed"}]) is True


def test_completion_with_empty_evidence_is_blocked():
    assert validate_completion([]) is False


def test_completion_without_evidence_is_blocked():
    assert validate_completion(None) is False
