from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

import http.client
from urllib.parse import urlparse


class McpError(Exception):
    pass


class McpConnectionError(McpError):
    pass


class McpRpcError(McpError):
    def __init__(self, *, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class McpTransport(Protocol):
    def request(self, payload: Dict[str, Any], *, timeout: float) -> Optional[Dict[str, Any]]:
        ...

    def close(self) -> None:
        ...


@dataclass
class HttpMcpTransport:
    url: str

    def request(self, payload: Dict[str, Any], *, timeout: float) -> Optional[Dict[str, Any]]:
        parsed = urlparse(self.url)
        if not parsed.hostname or not parsed.port:
            raise McpConnectionError(f"invalid MCP url: {self.url}")

        path = parsed.path or "/mcp"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
        try:
            conn.request(
                "POST",
                path,
                body=body,
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            data = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                raise McpConnectionError(f"MCP http error {resp.status}: {data}")
            if not data.strip():
                return None
            return json.loads(data)
        finally:
            conn.close()

    def close(self) -> None:
        return


@dataclass
class StdioMcpTransport:
    command: List[str]
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None

    _proc: subprocess.Popen[bytes] | None = None
    _lock: threading.Lock = threading.Lock()

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return

        full_env = os.environ.copy()
        if self.env:
            full_env.update({k: str(v) for k, v in self.env.items()})

        self._proc = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=full_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def request(self, payload: Dict[str, Any], *, timeout: float) -> Optional[Dict[str, Any]]:
        self._ensure_started()
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")

        with self._lock:
            self._proc.stdin.write(data)
            self._proc.stdin.flush()

            deadline = time.time() + max(timeout, 0.1)
            while True:
                if self._proc.poll() is not None:
                    stderr = b""
                    try:
                        if self._proc.stderr is not None:
                            stderr = self._proc.stderr.read() or b""
                    except Exception:
                        stderr = b""
                    raise McpConnectionError(
                        f"MCP stdio process exited ({self._proc.returncode}): {stderr.decode('utf-8', errors='replace')}"
                    )

                if time.time() > deadline:
                    raise McpConnectionError("MCP stdio request timeout")

                line = self._proc.stdout.readline()
                if not line:
                    time.sleep(0.01)
                    continue

                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue

                return json.loads(raw)

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None:
                self._proc.terminate()
        finally:
            self._proc = None


@dataclass
class McpClient:
    server_name: str
    transport: McpTransport
    timeout: float = 30.0
    protocol_version: str = "2026-02-28"

    _initialized: bool = False
    _request_id: int = 1
    _rpc_lock: threading.Lock = threading.Lock()

    def close(self) -> None:
        self.transport.close()

    def _next_id(self) -> int:
        with self._rpc_lock:
            rid = self._request_id
            self._request_id += 1
        return rid

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        resp = self.transport.request(payload, timeout=self.timeout)
        if resp is None:
            return None

        if "error" in resp:
            err = resp.get("error") or {}
            raise McpRpcError(
                code=int(err.get("code", -32000)),
                message=str(err.get("message", "MCP error")),
                data=err.get("data"),
            )

        return resp.get("result")

    def ensure_initialized(self) -> None:
        if self._initialized:
            return

        _ = self._rpc(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "clientInfo": {"name": "llm4vea", "version": "0.1"},
            },
        )
        self._initialized = True

    def list_tools(self) -> List[Dict[str, Any]]:
        self.ensure_initialized()
        result = self._rpc("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return list(tools) if isinstance(tools, list) else []

    def call_tool(self, *, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.ensure_initialized()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if isinstance(result, dict):
            return result
        return {"result": result}

    def read_resource(self, *, uri: str) -> Dict[str, Any]:
        self.ensure_initialized()
        result = self._rpc("resources/read", {"uri": uri})
        if isinstance(result, dict):
            return result
        return {"result": result}
