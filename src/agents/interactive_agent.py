from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from clients.llm_client import BaseLLMClient
from session_manager import SessionState, SessionManager, AgentPhase
from skills.skill_loader import load_skill, list_skills
from tools.tool_registry import ToolRegistry, ToolResult
from agents.prompts import PLAN_AGENT_SYSTEM_PROMPT, PWN_AGENT_SYSTEM_PROMPT, SKILL_PROMPT
from utils.logger import get_logger

logger = get_logger(__name__)


class StepResult:
    def __init__(
        self,
        step_type: str,
        content: str = "",
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict] = None,
        tool_result: Optional[ToolResult] = None,
        think: Optional[str] = None,
        phase: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.step_type = step_type
        self.content = content
        self.tool_name = tool_name
        self.tool_args = tool_args or {}
        self.tool_result = tool_result
        self.think = think
        self.phase = phase
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "step_type": self.step_type,
            "content": self.content,
        }
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.tool_args:
            result["tool_args"] = self.tool_args
        if self.tool_result:
            result["tool_result"] = {
                "returncode": self.tool_result.returncode,
                "stdout": self.tool_result.stdout,
                "stderr": self.tool_result.stderr,
            }
        if self.think:
            result["think"] = self.think
        if self.phase:
            result["phase"] = self.phase
        if self.error:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepResult":
        tool_result_data = data.get("tool_result")
        if isinstance(tool_result_data, dict):
            from tools.tool_registry import ToolResult
            tool_args = data.get("tool_args", {})
            if not isinstance(tool_args, dict):
                tool_args = {}
            
            tool_result = ToolResult(
                name=data.get("tool_name", ""),
                args=tool_args,
                returncode=tool_result_data.get("returncode", -1),
                stdout=tool_result_data.get("stdout", ""),
                stderr=tool_result_data.get("stderr", ""),
            )
        else:
            tool_result = None
        
        return cls(
            step_type=data.get("step_type", ""),
            content=data.get("content", ""),
            tool_name=data.get("tool_name"),
            tool_args=data.get("tool_args"),
            tool_result=tool_result,
            think=data.get("think"),
            phase=data.get("phase"),
            error=data.get("error"),
        )


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
        
        parts = [base_prompt, "\n\n", SKILL_PROMPT]
        if skill:
            parts.append("\n\n# Important Skills\n")
            parts.append(skill)
        parts.append("\n\n# Tools Index\n")
        parts.append(tools_index)
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
    ) -> Generator[StepResult, None, None]:
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
        
        def emit_result(result: StepResult) -> StepResult:
            self.session.step_results.append(result.to_dict())
            self.session_manager.save_session(self.session)
            return result
        
        while step_count < max_steps:
            step_count += 1
            
            try:
                resp = self.llm.complete(messages, tools=self.tools.schemas)
            except Exception as exc:
                logger.error(f"LLM complete failed: {exc}")
                yield emit_result(StepResult(
                    step_type="error",
                    error=f"LLM 调用失败: {exc}",
                ))
                return
            
            if not isinstance(resp, dict):
                yield emit_result(StepResult(
                    step_type="error",
                    error=f"LLM 返回格式错误: {type(resp)}",
                ))
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
                    
                    yield emit_result(StepResult(
                        step_type="tool_call",
                        tool_name=name,
                        tool_args=args,
                        phase=current_phase,
                    ))
                    
                    result: ToolResult = self.tools.run(name, **args)
                    
                    tool_history_entry = {
                        "name": name,
                        "args": args,
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                    self.session.tool_history.append(tool_history_entry)
                    
                    yield emit_result(StepResult(
                        step_type="tool_result",
                        tool_name=name,
                        tool_result=result,
                        phase=current_phase,
                    ))
                    
                    tool_content_parts: List[str] = []
                    tool_content_parts.append(f"# Tool result: {result.name}\n")
                    tool_content_parts.append(f"- args: {json.dumps(result.args, ensure_ascii=False)}\n")
                    tool_content_parts.append(f"- returncode: {result.returncode}\n\n")
                    tool_content_parts.append("## stdout\n\n```text\n")
                    tool_content_parts.append(result.stdout)
                    tool_content_parts.append("\n```\n")
                    tool_content_parts.append("\n## stderr\n\n```text\n")
                    tool_content_parts.append(result.stderr)
                    tool_content_parts.append("\n```\n")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": "".join(tool_content_parts),
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
                    yield emit_result(StepResult(
                        step_type="message",
                        content=raw,
                        phase=current_phase,
                    ))
                continue
            
            status = str(data.get("status", "")).lower()
            think = str(data.get("think", ""))
            plan_md = str(data.get("plan.md", ""))
            report_md = str(data.get("report.md", ""))
            
            if think.strip():
                yield emit_result(StepResult(
                    step_type="think",
                    content=think.strip(),
                    phase=current_phase,
                ))
                messages.append({"role": "assistant", "content": f"[Think] {think.strip()}"})
            
            if status == "finish":
                if current_phase == AgentPhase.PLAN.value:
                    if plan_md.strip():
                        self.plan_content = plan_md.strip()
                        self.plan_md.write_text(self.plan_content, encoding="utf-8")
                        self.session.plan_content = self.plan_content
                        self.session.plan_md_path = str(self.plan_md)
                        
                        yield emit_result(StepResult(
                            step_type="plan_complete",
                            content=self.plan_content,
                            phase=current_phase,
                        ))
                    
                    self.session.phase = AgentPhase.PWN.value
                    current_phase = AgentPhase.PWN.value
                    self.session_manager.save_session(self.session)
                    
                    yield emit_result(StepResult(
                        step_type="phase_change",
                        content="Plan 阶段完成，进入 Pwn 阶段",
                        phase=current_phase,
                    ))
                    
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
                        
                        yield emit_result(StepResult(
                            step_type="report_complete",
                            content=self.report_content,
                            phase=current_phase,
                        ))
                    
                    self.session.phase = AgentPhase.FINISHED.value
                    self.session_manager.save_session(self.session)
                    
                    yield emit_result(StepResult(
                        step_type="finished",
                        content="所有阶段已完成",
                        phase=AgentPhase.FINISHED.value,
                    ))
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
        self.session.tool_history = []
        self.session.step_results = []
        self.session_manager.save_session(self.session)

