from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from clients.llm_client import BaseLLMClient
from session_manager import SessionState, SessionManager, AgentPhase
from skills.skill_loader import load_skill, list_skills
from tools.tool_registry import ToolRegistry, ToolResult
from mcps.mcp_registry import McpRegistry
from agents.prompts import PLAN_AGENT_SYSTEM_PROMPT, PWN_AGENT_SYSTEM_PROMPT, SKILL_PROMPT
from utils.logger import get_logger

logger = get_logger(__name__)


class InteractivePwnAgent:
    def __init__(
            self,
            session: SessionState,
            session_manager: SessionManager,
    ):
        self.session = session
        self.session_manager = session_manager

        self.project_root = Path(session.project_root)
        self.run_dir = session_manager.get_run_dir(session.session_id)
        self.binary = Path(session.binary_path)

        self.tools = ToolRegistry()
        self.mcps = McpRegistry()
        self.llm: BaseLLMClient = self._build_llm()

        self._init_context()

    def _build_llm(self) -> BaseLLMClient:
        from clients.llm_client import OpenAIClient
        return OpenAIClient.build()

    def _init_context(self) -> None:
        self.poc_md = Path(self.session.poc_md_path) if self.session.poc_md_path else None
        self.plan_md = self.run_dir / "plan.md"
        self.exp_py = self.run_dir / "exp.py"

        if self.session.plan_md_path:
            self.plan_md = Path(self.session.plan_md_path)

        self.plan_content = self.session.plan_content
        self.report_content = self.session.report_content

    def _build_system_prompt(self, phase: str) -> str:
        if phase == AgentPhase.PLAN.value:
            base_prompt = PLAN_AGENT_SYSTEM_PROMPT
            skill = load_skill("core", "checksec")
        else:
            base_prompt = PWN_AGENT_SYSTEM_PROMPT
            skill = load_skill("core", "pwndbg") + load_skill("core", "pwntools")

        skills_index = list_skills()
        tools_index = self.tools.list_tools()
        mcps_index = self.mcps.list_mcps()

        parts = [base_prompt, "\n\n", SKILL_PROMPT]
        if skill:
            parts.append("\n\n# Important Skills\n")
            parts.append(skill)
        parts.append("\n\n# Tools Index\n")
        parts.append(tools_index)
        parts.append("\n\n# MCPs Index\n")
        parts.append(mcps_index)
        parts.append("\n\n# Skills Index\n")
        parts.append(skills_index)

        return "".join(parts)

    def _build_user_context(self, user_input: str, phase: str) -> str:
        parts: List[str] = []

        parts.append(f"# Task\n- binary_path: {self.binary}\n")

        if phase == AgentPhase.PLAN.value:
            if self.poc_md and self.poc_md.exists():
                parts.append(f"- poc_md_path: {self.poc_md}\n")
                parts.append("\n## Poc.md Content\n\n```markdown\n")
                parts.append(self.poc_md.read_text(encoding="utf-8"))
                parts.append("\n```\n")
        else:
            parts.append(f"- exp_path: {self.exp_py}\n")
            if self.plan_content:
                parts.append("\n## plan.md\n\n```markdown\n")
                parts.append(self.plan_content)
                parts.append("\n```\n")

        if user_input.strip():
            parts.append("\n## User Instruction\n\n")
            parts.append(user_input)
            parts.append("\n")

        return "".join(parts)

    def process_user_message(
            self,
            user_input: str,
            max_steps: int = 10,
    ):
        current_phase = self.session.phase

        if current_phase == AgentPhase.IDLE.value:
            current_phase = AgentPhase.PLAN.value
            self.session.phase = current_phase
            self.session_manager.save_session(self.session)

        system_prompt = self._build_system_prompt(current_phase)

        messages = list(self.session.messages)

        has_system_prompt = any(msg.get("role") == "system" for msg in messages)

        if not messages:
            user_context = self._build_user_context(user_input, current_phase)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_context},
            ]
        elif not has_system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
            if user_input.strip():
                messages.append({"role": "user", "content": user_input})
        else:
            if user_input.strip():
                messages.append({"role": "user", "content": user_input})

        step_count = 0

        while step_count < max_steps:
            step_count += 1

            try:
                resp = self.llm.complete(messages, tools=(self.tools.schemas + self.mcps.schemas))
            except Exception as exc:
                logger.error(f"LLM complete failed: {exc}")
                return

            if not isinstance(resp, dict):
                return

            messages.append(resp)

            tool_calls = resp.get("tool_calls", None)
            if isinstance(tool_calls, list) and tool_calls:
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue

                    call_id = str(call.get("id", "")).strip()
                    fn = call.get("function", {})
                    if not isinstance(fn, dict):
                        continue

                    name = str(fn.get("name", "")).strip()
                    if not name:
                        continue

                    raw_args = fn.get("arguments", "{}")
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else {}
                    except Exception:
                        args = {}
                    if not isinstance(args, dict):
                        args = {}

                    logger.info(f"Tool call: {name} with args: {args}")

                    if self.tools.has_tool(name):
                        result: ToolResult = self.tools.run(name, **args)
                        tool_kind = "tool"
                    elif self.mcps.is_mcp_tool(name):
                        result = self.mcps.run(name, **args)
                        tool_kind = "mcp"
                    else:
                        result = self.tools.run(name, **args)
                        tool_kind = "tool"

                    meta = result.metadata or {}
                    meta.setdefault("tool_kind", tool_kind)

                    tool_result_data = {
                        "name": name,
                        "args": args,
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "metadata": meta,
                    }

                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(tool_result_data, ensure_ascii=False),
                    })

                self.session.messages = messages
                self.session_manager.save_session(self.session)
                continue

            raw = resp.get("content", "")

            try:
                data = json.loads(raw) if raw.strip() else {}
            except Exception:
                if raw.strip():
                    messages.append({"role": "assistant", "content": raw})
                    self.session.messages = messages
                    self.session_manager.save_session(self.session)
                continue

            status = str(data.get("status", "")).lower()
            plan_md = str(data.get("plan.md", ""))
            report_md = str(data.get("report.md", ""))

            if status == "finish":
                if current_phase == AgentPhase.PLAN.value:
                    if plan_md.strip():
                        self.plan_content = plan_md.strip()
                        self.plan_md.write_text(self.plan_content, encoding="utf-8")
                        self.session.plan_content = self.plan_content
                        self.session.plan_md_path = str(self.plan_md)

                    self.session.phase = AgentPhase.PWN.value
                    current_phase = AgentPhase.PWN.value
                    self.session_manager.save_session(self.session)

                    system_prompt = self._build_system_prompt(current_phase)
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": self._build_user_context("", current_phase)},
                    ]
                    continue

                elif current_phase == AgentPhase.PWN.value:
                    if report_md.strip():
                        self.report_content = report_md.strip()
                        report_path = self.run_dir / "report.md"
                        report_path.write_text(self.report_content, encoding="utf-8")
                        self.session.report_content = self.report_content

                    self.session.phase = AgentPhase.FINISHED.value
                    self.session_manager.save_session(self.session)
                    return

            self.session.messages = messages
            self.session_manager.save_session(self.session)
            break

    def switch_phase(self, phase: str) -> None:
        if phase not in {AgentPhase.PLAN.value, AgentPhase.PWN.value, AgentPhase.IDLE.value}:
            raise ValueError(f"Invalid phase: {phase}")
        self.session.phase = phase
        self.session.messages = [
            msg for msg in self.session.messages if msg.get("role") != "system"
        ]
        self.session_manager.save_session(self.session)

    def reset_phase(self, phase: str = AgentPhase.PLAN.value) -> None:
        self.session.phase = phase
        self.session.messages = []
        self.session_manager.save_session(self.session)
