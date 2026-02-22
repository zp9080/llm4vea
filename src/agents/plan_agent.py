from __future__ import annotations

import json
from datetime import datetime
from typing import List

from agents.base_agent import BaseAgent, RunContext
from skills.skill_loader import (
    list_skills,
    load_skill
)
from tools.tool_registry import ToolResult
from agents.prompts import PLAN_AGENT_SYSTEM_PROMPT, SKILL_PROMPT
from utils.logger import (
    get_logger,
    log_section,
    log_success,
    log_error,
    log_warning,
    log_info,
    log_step,
    log_tool_call,
    log_tool_result
)

logger = get_logger(__name__)


class PlanAgent(BaseAgent):
    """多轮 LLM 驱动的规划 Agent。

    设计要点：
    - 外部输入尽量简单：二进制路径 + poc_md；
    - skills 作为高优先级“工具”，通过 <skills> 索引暴露 name/description，是否深入阅读由 LLM 自己决定；
    - 多轮循环由 LLM 通过 status 决定何时结束，我们只设置最大轮数上限防止死循环。"""

    def __init__(self, ctx: RunContext) -> None:
        super().__init__(ctx, name="PlanAgent")

    def run(self) -> None:  # type: ignore[override]
        ctx = self.ctx
        tools = ctx.tools
        binary = ctx.binary
        poc_md = ctx.poc_md
        llm = ctx.llm

        log_section(logger, "🚀 PlanAgent Starting")
        log_info(logger, f"Binary: {binary}")
        if poc_md:
            log_info(logger, f"Poc: {poc_md}")

        skills_index = list_skills()
        tools_index = tools.list_tools()
        skill_for_plan = load_skill("core", "checksec")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        plan_path = ctx.run_dir / "plan.md"

        user_parts: List[str] = ["# Task\n", f"- binary_path: {binary}\n"]
        if poc_md is not None:
            user_parts.append(f"- poc_md_path: {poc_md}\n")
        user_parts.append(f"- generated_at: {now}\n")

        if poc_md is not None and poc_md.exists():
            user_parts.append("\n## Input Poc.md\n\n```markdown\n")
            user_parts.append(poc_md.read_text(encoding="utf-8"))
            user_parts.append("\n```\n")

        user_base_context = "".join(user_parts)

        system_parts: List[str] = []
        if skill_for_plan:
            system_parts.append("\n# Important Skill For PlanAgent\n")
            system_parts.append(skill_for_plan)

        system_parts.append("\n# Tools index\n")
        system_parts.append(tools_index)

        system_parts.append("\n# Skills index\n")
        system_parts.append(skills_index)

        system_base_context = "".join(system_parts)

        # 2. LLM 自主控制的多轮循环
        max_rounds = 15
        final_plan: str | None = None

        log_info(logger, f"Starting multi-round LLM loop (max rounds: {max_rounds})")

        system_prompt = PLAN_AGENT_SYSTEM_PROMPT + "\n\n" + SKILL_PROMPT + "\n\n" + system_base_context
        user_prompt = user_base_context
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        log_info(logger, f"System Prompt: {system_prompt}")

        try:
            for round_idx in range(1, max_rounds + 1):
                log_step(logger, round_idx, max_rounds, "Processing LLM request")
                try:
                    resp = llm.complete(messages, tools=tools.schemas)
                except Exception as exc:
                    log_error(logger, f"Failed to complete plan in round {round_idx}: {exc}")
                    raise RuntimeError(f"Failed to complete plan: {exc}") from exc

                if not isinstance(resp, dict):
                    raise RuntimeError(f"response is not a dict: {resp}")

                messages.append(resp)

                # 处理tool_calls
                tool_calls = resp.get("tool_calls", None)
                if isinstance(tool_calls, list) and tool_calls:
                    log_info(logger, f"Received {len(tool_calls)} tool calls in round {round_idx}")
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
                        log_tool_call(logger, name, args)
                        result: ToolResult = tools.run(name, **args)
                        log_tool_result(logger, name, result.returncode, result.stdout, result.stderr)
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
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": "".join(tool_content_parts),
                            }
                        )
                    continue

                # 处理返回的json数据
                raw = resp.get("content", "")
                log_info(logger, f"LLM Response Content:\n{str(raw)}")

                try:
                    data = json.loads(raw)
                except Exception:
                    log_warning(logger, f"Invalid JSON response in round {round_idx}: {raw[:100]}...")
                    messages.append({"role": "user", "content": "返回的内容不是纯json，请重新返回"})
                    continue

                try:
                    status = str(data.get("status", "")).lower()
                    plan_md = str(data.get("plan.md", ""))
                    think = str(data.get("think", ""))
                except Exception as e:
                    log_error(logger, f"Failed to parse JSON fields in round {round_idx}: {e}")
                    messages.append({"role": "user", "content": f"返回的json字段解析失败: {e}，请重新返回"})
                    continue

                if status not in {"continue", "finish"}:
                    log_warning(logger, f"Invalid status '{status}' in round {round_idx}")
                    messages.append({"role": "user", "content": "返回的status应当是continue或finish两者状态之一，继续分析任务"})
                    continue

                if think.strip():
                    messages.append({"role": "assistant", "content": f"[Think] {think.strip()}"})

                if status == "finish" and plan_md.strip():
                    log_success(logger, f"PlanAgent finished in round {round_idx}")
                    final_plan = plan_md.strip()
                    break

                messages.append({"role": "user", "content": "继续"})
        finally:
            (self.ctx.run_dir / "messages.json").write_text(
                json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            log_info(logger, f"Messages saved to: {self.ctx.run_dir / 'messages.json'}")

        log_success(logger, f"Plan written to: {plan_path}")
        # 3. 存储plan.md
        if final_plan is None:
            log_error(logger, "PlanAgent failed: no final plan generated")
            raise RuntimeError("PlanAgent执行失败，没有返回plan.md")
        plan_path.write_text(final_plan, encoding="utf-8")
        log_section(logger, "✅ PlanAgent Completed Successfully")
