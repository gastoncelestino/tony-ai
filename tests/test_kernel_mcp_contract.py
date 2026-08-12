from __future__ import annotations

import json

import pytest

from kernel import mcp_server


@pytest.mark.mcp
def test_parse_line_returns_jsonrpc_parse_error_for_invalid_json() -> None:
    response = mcp_server.parse_line('{"jsonrpc":')

    assert response["jsonrpc"] == "2.0"
    assert response["id"] is None
    assert response["error"]["code"] == -32700


@pytest.mark.mcp
def test_parse_line_rejects_non_object_requests() -> None:
    response = mcp_server.parse_line("[]")

    assert response["error"]["code"] == -32600
    assert "expected an object" in response["error"]["message"]


@pytest.mark.mcp
def test_initialize_contract() -> None:
    response = mcp_server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["serverInfo"]["name"] == "tony-kernel"


@pytest.mark.mcp
def test_tools_list_exposes_schemas() -> None:
    response = mcp_server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )

    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert "kernel_can_start_phase" in names
    assert "kernel_record_phase_completion" in names
    assert all("inputSchema" in tool for tool in tools)


@pytest.mark.mcp
def test_tools_call_success_uses_text_content_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        mcp_server.TOOLS,
        "test_probe",
        {
            "description": "test-only probe",
            "inputSchema": {"type": "object"},
            "handler": lambda args: {"received": args},
        },
    )

    response = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "test_probe", "arguments": {"ok": True}},
        }
    )

    assert response["result"]["content"][0]["type"] == "text"
    assert json.loads(response["result"]["content"][0]["text"]) == {
        "received": {"ok": True}
    }


@pytest.mark.mcp
def test_unknown_tool_returns_jsonrpc_method_not_found() -> None:
    response = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "does_not_exist", "arguments": {}},
        }
    )

    assert response["error"]["code"] == -32601
    assert "does_not_exist" in response["error"]["message"]


@pytest.mark.mcp
def test_handler_exception_is_explicit_is_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(_args: dict) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setitem(
        mcp_server.TOOLS,
        "test_explode",
        {
            "description": "test-only failing handler",
            "inputSchema": {"type": "object"},
            "handler": explode,
        },
    )

    response = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "test_explode", "arguments": {}},
        }
    )

    assert response["result"]["isError"] is True
    assert "boom" in response["result"]["content"][0]["text"]


@pytest.mark.mcp
def test_unknown_method_returns_method_not_found() -> None:
    response = mcp_server.handle(
        {"jsonrpc": "2.0", "id": 6, "method": "unknown/method"}
    )

    assert response["error"]["code"] == -32601


@pytest.mark.mcp
def test_notification_does_not_generate_response() -> None:
    assert (
        mcp_server.handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        is None
    )


@pytest.mark.mcp
def test_ping_contract() -> None:
    response = mcp_server.handle(
        {"jsonrpc": "2.0", "id": 7, "method": "ping"}
    )

    assert response == {"jsonrpc": "2.0", "id": 7, "result": {}}
