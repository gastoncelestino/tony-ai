from __future__ import annotations

import json
import unittest
from unittest import mock

import pytest

from kernel import mcp_server


@pytest.mark.mcp
class TestMcpContract(unittest.TestCase):
    def test_parse_line_returns_jsonrpc_parse_error_for_invalid_json(self) -> None:
        response = mcp_server.parse_line('{"jsonrpc":')
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertIsNone(response["id"])
        self.assertEqual(response["error"]["code"], -32700)

    def test_parse_line_rejects_non_object_requests(self) -> None:
        response = mcp_server.parse_line("[]")
        self.assertEqual(response["error"]["code"], -32600)
        self.assertIn("expected an object", response["error"]["message"])

    def test_initialize_contract(self) -> None:
        response = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(response["result"]["serverInfo"]["name"], "tony-kernel")

    def test_tools_list_exposes_schemas(self) -> None:
        response = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = response["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertIn("kernel_can_start_phase", names)
        self.assertIn("kernel_record_phase_completion", names)
        self.assertTrue(all("inputSchema" in tool for tool in tools))

    def test_tools_call_success_uses_text_content_envelope(self) -> None:
        probe = {
            "description": "test-only probe",
            "inputSchema": {"type": "object"},
            "handler": lambda args: {"received": args},
        }
        with mock.patch.dict(mcp_server.TOOLS, {"test_probe": probe}, clear=False):
            response = mcp_server.handle({
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "test_probe", "arguments": {"ok": True}},
            })
        self.assertEqual(response["result"]["content"][0]["type"], "text")
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]), {"received": {"ok": True}})

    def test_unknown_tool_returns_jsonrpc_method_not_found(self) -> None:
        response = mcp_server.handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "does_not_exist", "arguments": {}},
        })
        self.assertEqual(response["error"]["code"], -32601)
        self.assertIn("does_not_exist", response["error"]["message"])

    def test_handler_exception_is_explicit_is_error(self) -> None:
        def explode(_args: dict) -> dict:
            raise RuntimeError("boom")

        probe = {
            "description": "test-only failing handler",
            "inputSchema": {"type": "object"},
            "handler": explode,
        }
        with mock.patch.dict(mcp_server.TOOLS, {"test_explode": probe}, clear=False):
            response = mcp_server.handle({
                "jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {"name": "test_explode", "arguments": {}},
            })
        self.assertTrue(response["result"]["isError"])
        self.assertIn("boom", response["result"]["content"][0]["text"])

    def test_unknown_method_returns_method_not_found(self) -> None:
        response = mcp_server.handle({"jsonrpc": "2.0", "id": 6, "method": "unknown/method"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_notification_does_not_generate_response(self) -> None:
        self.assertIsNone(mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_ping_contract(self) -> None:
        response = mcp_server.handle({"jsonrpc": "2.0", "id": 7, "method": "ping"})
        self.assertEqual(response, {"jsonrpc": "2.0", "id": 7, "result": {}})


if __name__ == "__main__":
    unittest.main()
