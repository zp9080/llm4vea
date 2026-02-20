from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from clients.llm_client import BaseLLMClient
from tools.tool_registry import ToolRegistry


@dataclass
class RunContext:
    """单次运行的上下文信息。

    - binary: 当前调试/利用的目标二进制文件路径
    - info_md: Plan 阶段的补充信息 markdown（例如 poc 说明）
    - plan_md: Plan 生成或外部提供的 plan.md 路径
    - llm: 提供 complete(messages) -> str 的 LLM 客户端实例
    """

    project_root: Path
    run_dir: Path
    binary: Path
    info_md: Optional[Path]
    plan_md: Optional[Path]
    tools: ToolRegistry
    llm: BaseLLMClient


class BaseAgent:
    """Agent 抽象基类，负责消息记录与基础上下文管理。

    具体的 LLM 调用逻辑由上层集成方实现，这里只聚焦于输入输出管线和工具调用。
    """

    def __init__(self, ctx: RunContext, name: str) -> None:
        self.ctx = ctx
        self.name = name
        self.messages: List[Dict[str, Any]] = []

    def save_messages(self) -> None:
        if not self.messages:
            return
        path = self.ctx.run_dir / "messages.json"
        existing: List[Dict[str, Any]] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.extend(self.messages)
        path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    # 预留 run 接口，由子类实现
    def run(self) -> None:  # pragma: no cover - 抽象接口
        raise NotImplementedError
