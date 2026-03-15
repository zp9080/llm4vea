from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcps.mcp_client import (
    HttpMcpTransport,
    McpClient,
    McpConnectionError,
    McpRpcError,
    StdioMcpTransport,
)
from tools.tool_registry import ToolResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MCPS_JSON = PROJECT_ROOT / "inputs" / "mcps.json"


def _normalize_name(value: str) -> str:
    value = value.strip()
    if not value:
        return "_"
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    return value[:64]


def _bounded_tool_name(prefix: str, server: str, tool: str) -> str:
    base = f"{prefix}__{_normalize_name(server)}__{_normalize_name(tool)}"
    if len(base) <= 64:
        return base
    digest = hashlib.md5(base.encode("utf-8")).hexdigest()[:8]
    head = base[: max(0, 64 - 9)]
    return f"{head}_{digest}"


@dataclass
class McpServerConfig:
    name: str
    transport: str
    description: str = ""

    # http
    url: Optional[str] = None

    # stdio
    command: Optional[List[str]] = None
    args: List[str] = None
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None

    timeout: float = 30.0

    # Whether to expand remote tools to individual OpenAI function tools.
    expose_tools: bool = False
    max_tools_in_prompt: int = 50

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "McpServerConfig":
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("mcp server name is required")

        transport = str(data.get("transport", "http")).strip().lower()
        description = str(data.get("description", "")).strip()

        args = data.get("args")
        if not isinstance(args, list):
            args = []

        env = data.get("env")
        if not isinstance(env, dict):
            env = None

        command = data.get("command")
        if isinstance(command, str):
            command = [command]
        if not isinstance(command, list):
            command = None

        return cls(
            name=name,
            transport=transport,
            description=description,
            url=str(data.get("url")).strip() if data.get("url") else None,
            command=[str(x) for x in command] if command else None,
            args=[str(x) for x in args],
            cwd=str(data.get("cwd")).strip() if data.get("cwd") else None,
            env={str(k): str(v) for k, v in env.items()} if env else None,
            timeout=float(data.get("timeout", 30.0)),
            expose_tools=bool(data.get("expose_tools", False)),
            max_tools_in_prompt=int(data.get("max_tools_in_prompt", 50)),
        )


class McpRegistry:
    """MCP system: manage MCP servers & remote tools.

    This is intentionally separated from the local tools system.

    OpenAI function tool schemas:
    - Built-in MCP management tools: mcp_list_tools, mcp_call_tool
    - Optional expanded remote tools: mcp__{server}__{tool}
    """

    BUILTIN_PREFIX = "mcp"

    def __init__(self) -> None:
        self._configs: Dict[str, McpServerConfig] = {}
        self._clients: Dict[str, McpClient] = {}

        # openai_name -> (server_name, remote_tool_name)
        self._remote_tool_map: Dict[str, Tuple[str, str]] = {}
        self._remote_tool_schemas: Dict[str, Dict[str, Any]] = {}

        self._load_configs()

    def _load_configs(self) -> None:
        if not MCPS_JSON.exists():
            self._configs = {}
            return

        try:
            data = json.loads(MCPS_JSON.read_text(encoding="utf-8"))
        except Exception:
            self._configs = {}
            return

        servers = data.get("mcps", [])
        if not isinstance(servers, list):
            self._configs = {}
            return

        configs: Dict[str, McpServerConfig] = {}
        for item in servers:
            if not isinstance(item, dict):
                continue
            try:
                cfg = McpServerConfig.from_dict(item)
            except Exception:
                continue
            configs[cfg.name] = cfg

        self._configs = configs

    def list_mcps(self) -> str:
        parts: List[str] = ["<mcps>\n"]
        if not self._configs:
            parts.append("\n(未配置 MCP Server：请创建 inputs/mcps.json)\n")
            parts.append("\n</mcps>\n")
            return "".join(parts)

        for name, cfg in self._configs.items():
            status = "connected" if name in self._clients else "disconnected"
            parts.append(f"\n## {name}\n")
            if cfg.description:
                parts.append(f"\n{cfg.description}\n")
            parts.append(f"\n- transport: {cfg.transport}\n")
            if cfg.transport == "http" and cfg.url:
                parts.append(f"- url: {cfg.url}\n")
            if cfg.transport == "stdio":
                cmd = " ".join((cfg.command or []) + (cfg.args or []))
                parts.append(f"- command: {cmd}\n")
            parts.append(f"- status: {status}\n")
            parts.append(f"- expose_tools: {cfg.expose_tools}\n")

        parts.append("\n</mcps>\n")
        return "".join(parts)

    def _get_client(self, server_name: str) -> McpClient:
        cfg = self._configs.get(server_name)
        if not cfg:
            raise McpConnectionError(f"unknown mcp server: {server_name}")

        if server_name in self._clients:
            return self._clients[server_name]

        if cfg.transport == "http":
            if not cfg.url:
                raise McpConnectionError(f"mcp server '{server_name}' missing url")
            transport = HttpMcpTransport(cfg.url)
        elif cfg.transport == "stdio":
            if not cfg.command:
                raise McpConnectionError(f"mcp server '{server_name}' missing command")
            transport = StdioMcpTransport(
                command=list(cfg.command) + list(cfg.args or []),
                cwd=cfg.cwd,
                env=cfg.env,
            )
        else:
            raise McpConnectionError(f"unsupported mcp transport: {cfg.transport}")

        client = McpClient(server_name=server_name, transport=transport, timeout=cfg.timeout)
        self._clients[server_name] = client
        return client

    def _refresh_remote_tool_schemas(self, server_name: str, tools: List[Dict[str, Any]]) -> None:
        cfg = self._configs.get(server_name)
        if not cfg or not cfg.expose_tools:
            return

        count = 0
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            remote_name = str(tool.get("name", "")).strip()
            if not remote_name:
                continue

            openai_name = _bounded_tool_name(self.BUILTIN_PREFIX, server_name, remote_name)
            input_schema = tool.get("inputSchema")
            if not isinstance(input_schema, dict):
                input_schema = {"type": "object", "properties": {}, "required": []}

            schema = {
                "type": "function",
                "function": {
                    "name": openai_name,
                    "description": str(tool.get("description", "")).strip() or f"MCP:{server_name}/{remote_name}",
                    "parameters": input_schema,
                },
            }
            self._remote_tool_map[openai_name] = (server_name, remote_name)
            self._remote_tool_schemas[openai_name] = schema
            count += 1

        return

    @property
    def schemas(self) -> List[Dict[str, Any]]:
        builtin = [
            {
                "type": "function",
                "function": {
                    "name": "mcp_list_tools",
                    "description": "List tools from an MCP server (and refresh local cache).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "server": {"type": "string", "description": "MCP server name from <mcps>"},
                        },
                        "required": ["server"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mcp_call_tool",
                    "description": "Call a tool on an MCP server.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "server": {"type": "string", "description": "MCP server name from <mcps>"},
                            "name": {"type": "string", "description": "Remote MCP tool name"},
                            "arguments": {
                                "type": "object",
                                "description": "Tool arguments object",
                                "additionalProperties": True,
                            },
                        },
                        "required": ["server", "name"],
                    },
                },
            },
        ]

        dynamic = list(self._remote_tool_schemas.values())
        return builtin + dynamic

    def is_mcp_tool(self, tool_name: str) -> bool:
        if tool_name in {"mcp_list_tools", "mcp_call_tool"}:
            return True
        return tool_name in self._remote_tool_map

    def run(self, tool_name: str, **kwargs: Any) -> ToolResult:
        try:
            if tool_name == "mcp_list_tools":
                server = str(kwargs.get("server", "")).strip()
                include_schema = bool(kwargs.get("include_schema", True))
                if not server:
                    raise McpConnectionError("server is required")

                client = self._get_client(server)
                tools = client.list_tools()
                self._refresh_remote_tool_schemas(server, tools)

                if not include_schema:
                    tools = [
                        {"name": t.get("name"), "description": t.get("description")}
                        for t in tools
                        if isinstance(t, dict)
                    ]

                return ToolResult(
                    name=tool_name,
                    args={"server": server, "include_schema": include_schema},
                    stdout=json.dumps({"tools": tools}, ensure_ascii=False, indent=2),
                    stderr="",
                    returncode=0,
                    metadata={"tool_kind": "mcp", "mcp_server": server, "op": "list"},
                )

            if tool_name == "mcp_call_tool":
                server = str(kwargs.get("server", "")).strip()
                remote_name = str(kwargs.get("name", "")).strip()
                arguments = kwargs.get("arguments", {})
                if not isinstance(arguments, dict):
                    arguments = {}

                if not server or not remote_name:
                    raise McpConnectionError("server and name are required")

                client = self._get_client(server)
                resp = client.call_tool(name=remote_name, arguments=arguments)

                content_text = ""
                content = resp.get("content")
                if isinstance(content, list):
                    texts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            texts.append(str(item.get("text", "")))
                    content_text = "\n".join(texts).strip()

                return ToolResult(
                    name=tool_name,
                    args={"server": server, "name": remote_name, "arguments": arguments},
                    stdout=content_text or json.dumps(resp, ensure_ascii=False, indent=2),
                    stderr="" if not resp.get("isError") else json.dumps(resp, ensure_ascii=False, indent=2),
                    returncode=0 if not resp.get("isError") else 1,
                    metadata={
                        "tool_kind": "mcp",
                        "mcp_server": server,
                        "mcp_tool": remote_name,
                        "structuredContent": resp.get("structuredContent"),
                        "raw": resp,
                    },
                )

            if tool_name in self._remote_tool_map:
                server, remote_name = self._remote_tool_map[tool_name]
                arguments = dict(kwargs)
                client = self._get_client(server)
                resp = client.call_tool(name=remote_name, arguments=arguments)

                content_text = ""
                content = resp.get("content")
                if isinstance(content, list):
                    texts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            texts.append(str(item.get("text", "")))
                    content_text = "\n".join(texts).strip()

                return ToolResult(
                    name=tool_name,
                    args=arguments,
                    stdout=content_text or json.dumps(resp, ensure_ascii=False, indent=2),
                    stderr="" if not resp.get("isError") else json.dumps(resp, ensure_ascii=False, indent=2),
                    returncode=0 if not resp.get("isError") else 1,
                    metadata={
                        "tool_kind": "mcp",
                        "mcp_server": server,
                        "mcp_tool": remote_name,
                        "structuredContent": resp.get("structuredContent"),
                        "raw": resp,
                    },
                )

            return ToolResult(
                name=tool_name,
                args=dict(kwargs),
                stdout="",
                stderr=f"unknown mcp tool: {tool_name}",
                returncode=1,
                metadata={"error": "unknown-tool", "tool_kind": "mcp"},
            )

        except (McpConnectionError, McpRpcError) as exc:
            return ToolResult(
                name=tool_name,
                args=dict(kwargs),
                stdout="",
                stderr=str(exc),
                returncode=1,
                metadata={"tool_kind": "mcp", "error": "mcp-error"},
            )
        except Exception as exc:
            return ToolResult(
                name=tool_name,
                args=dict(kwargs),
                stdout="",
                stderr=f"mcp tool failed: {exc}",
                returncode=1,
                metadata={"tool_kind": "mcp", "error": "mcp-exception"},
            )
