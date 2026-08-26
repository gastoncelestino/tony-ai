"""Tests for the minimal Kernel tool capability policy."""
from kernel.tool_policy import authorize_tool


def test_allowed_tool_in_phase():
    decision = authorize_tool("explore", "read")
    assert decision.allowed is True


def test_disallowed_tool_in_phase_is_blocked():
    decision = authorize_tool("explore", "write")
    assert decision.allowed is False


def test_unknown_phase_is_blocked():
    decision = authorize_tool("unknown", "read")
    assert decision.allowed is False
