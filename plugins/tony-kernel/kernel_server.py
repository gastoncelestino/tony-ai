#!/usr/bin/env python3
"""
Tony Kernel HTTP Server

Simple HTTP server that wraps the KernelOrchestrator for the tony-kernel plugin.
"""
from __future__ import annotations
import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

# Add kernel to path
sys.path.insert(0, '/workspace/7cf8dcfc-72e2-49b9-9795-75440ba1be96/sessions/agent_0a609c26-9e31-4ad3-abf7-5af14c9f5367')

from kernel.orchestrator_integration import (
    create_kernel_orchestrator, 
    OrchestrationDecision,
    OrchestrationResult
)
from kernel.schemas import Phase, ArtifactRef, Evidence, EvidenceType, EvidenceStatus


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server."""
    daemon_threads = True


class KernelHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for Kernel API."""
    
    kernel_instance = None
    _init_lock = threading.Lock()
    
    def __init__(self, *args, **kwargs):
        # Lazy initialization of kernel
        if KernelHTTPHandler.kernel_instance is None:
            with KernelHTTPHandler._init_lock:
                if KernelHTTPHandler.kernel_instance is None:
                    from kernel.orchestrator_integration import create_kernel_orchestrator
                    KernelHTTPHandler.kernel_instance = create_kernel_orchestrator("default", "default")
        super().__init__(*args, **kwargs)
    
    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())
    
    def _parse_body(self) -> dict:
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode('utf-8')
        return json.loads(body) if body else {}
    
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if self.server.kernel:
                self.wfile.write(json.dumps(self.server.kernel.get_status(), default=str).encode())
            else:
                self.wfile.write(json.dumps({"error": "kernel not initialized"}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        data = self._parse_body()
        
        try:
            if self.path == "/can_start_phase":
                phase = data.get("phase", "")
                result = self.server.kernel.can_start_phase(phase)
                self._send_json(200, {
                    "decision": result.decision.value,
                    "reason": result.reason,
                    "current_phase": result.current_phase,
                    "requested_phase": result.requested_phase,
                    "missing_artifacts": list(result.missing_artifacts),
                    "missing_evidence": list(result.missing_evidence),
                    "scope_violations": list(result.scope_violations),
                    "retry_status": result.retry_status,
                    "next_action": result.next_action,
                })
            
            elif self.path == "/record_delegation":
                self.server.kernel.record_delegation(
                    data.get("phase", ""),
                    data.get("sub_agent", ""),
                    data.get("task_id")
                )
                self._send_json(200, {"ok": True})
            
            elif self.path == "/record_phase_completion":
                artifacts = data.get("artifacts", [])
                evidence = data.get("evidence", [])
                
                # Convert artifacts to ArtifactRef
                artifact_refs = []
                for art in artifacts:
                    if isinstance(art, dict):
                        artifact_refs.append(ArtifactRef(
                            kind=art.get("kind", ""),
                            path=art.get("path", ""),
                            store=art.get("store", "tonymem"),
                            hash=art.get("hash"),
                            validated=art.get("validated", False),
                        ))
                    else:
                        artifact_refs.append(art)
                
                result = self.server.kernel.record_phase_completion(
                    data.get("phase", ""),
                    tuple(artifact_refs)
                )
                
                self._send_json(200, {
                    "decision": result.decision.value,
                    "reason": result.reason,
                    "current_phase": result.current_phase,
                    "requested_phase": result.requested_phase,
                })
            
            elif self.path == "/record_delegation":
                self.server.kernel.record_delegation(
                    data.get("phase", ""),
                    data.get("sub_agent", ""),
                    data.get("task_id")
                )
                self._send_json(200, {"ok": True})
            
            elif self.path == "/get_next_task":
                task = self.server.kernel.get_next_task()
                if task:
                    self._send_json(200, {
                        "id": task.id,
                        "description": task.description,
                        "phase": task.phase.value,
                        "dependencies": task.dependencies,
                        "files": task.files,
                    })
                else:
                    self._send_json(200, {})
            
            elif self.path == "/check_scope":
                result = self.server.kernel.check_scope(
                    data.get("git_diff", ""),
                    tuple(data.get("allowed_files", []))
                )
                self._send_json(200, {
                    "decision": result.decision.value,
                    "reason": result.reason,
                    "current_phase": result.current_phase,
                    "scope_violations": list(result.scope_violations),
                })
            
            elif self.path == "/verify_phase_checksum":
                result = self.server.kernel.verify_phase_checksum(data.get("phase", ""))
                self._send_json(200, result)
            
            elif self.path == "/record_phase_checksum":
                artifacts = data.get("artifacts", [])
                self.server.kernel.record_phase_checksum(
                    data.get("phase", ""),
                    [ArtifactRef(**a) if isinstance(a, dict) else a for a in artifacts]
                )
                self._send_json(200, {"ok": True})
            
            elif self.path == "/get_status":
                self._send_json(200, self.server.kernel.get_status())
            
            else:
                self.send_response(404)
                self.end_headers()
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logging


def run_server(port: int = 7438):
    """Run the HTTP server."""
    from socketserver import ThreadingMixIn
    from http.server import HTTPServer
    
    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
    
    server = HTTPServer(('127.0.0.1', port), KernelHTTPHandler)
    server.kernel = None  # Will be set in handler __init__
    
    print(f"[tony-kernel] HTTP server starting on 127.0.0.1:{port}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7438
    run_server(port)