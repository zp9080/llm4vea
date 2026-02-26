from __future__ import annotations

import json
from pathlib import Path

from agents.base_agent import BaseAgent, RunContext
from tools.tool_registry import ToolResult
from skills.skill_loader import load_skill, list_skills
from agents.prompts import PWN_AGENT_SYSTEM_PROMPT, SKILL_PROMPT
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


class PwnAgent(BaseAgent):
    """多轮 LLM 驱动的 EXP 生成 Agent。

    设计要点：
    - 每一轮由 LLM 决定是继续迭代(`status=continue`)还是结束(`status=finish`)；
    - LLM 通过工具直接写 exp.py 并执行 exp_runner，工具调用结果自动进入 messages；
    - 设定最大轮数上限防止死循环。"""

    def __init__(self, ctx: RunContext) -> None:
        super().__init__(ctx, name="PwnAgent")

    def run(self) -> None:  # type: ignore[override]
        ctx = self.ctx
        binary = ctx.binary
        tools = ctx.tools
        plan_md = ctx.plan_md
        llm = ctx.llm

        exp_py = ctx.run_dir / "exp.py"

        log_section(logger, "🚀 PwnAgent Starting")
        log_info(logger, f"Binary: {binary}")
        log_info(logger, f"Plan MD: {plan_md}")
        log_info(logger, f"Exp path: {exp_py}")

        plan_text = ""
        if plan_md is not None and Path(plan_md).exists():
            plan_text = Path(plan_md).read_text(encoding="utf-8")
            log_success(logger, f"Loaded plan from {plan_md}")

        skill_for_pwn = load_skill("core", "pwndbg") + load_skill("core", "pwntools")
        skills_index = list_skills()
        tools_index = tools.list_tools()

        user_parts: List[str] = []
        user_parts.append(f"# Task\n- binary_path: {binary}\n- exp_path: {exp_py}\n")
        if plan_text:
            user_parts.append("\n# plan.md\n\n" + plan_text + "\n")
        user_base_context = "".join(user_parts)

        system_parts: List[str] = []
        if skill_for_pwn:
            system_parts.append("\n# Important Skill For PwnAgent\n")
            system_parts.append(skill_for_pwn)
        system_parts.append("\n# Tools index\n")
        system_parts.append(tools_index)
        system_parts.append("\n# Skills index\n")
        system_parts.append(skills_index)
        system_base_context = "".join(system_parts)

        max_rounds = 30
        final_report_md: str | None = None

        log_info(logger, f"Starting multi-round LLM loop (max rounds: {max_rounds})")

        system_prompt = PWN_AGENT_SYSTEM_PROMPT + "\n\n" + SKILL_PROMPT + "\n\n" + system_base_context
        user_prompt = user_base_context
        messages = [
            {"role": "system", "content": system_prompt },
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
                        
                        tool_result_data = {
                            "name": name,
                            "args": args,
                            "returncode": result.returncode,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                        }
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(tool_result_data, ensure_ascii=False),
                        })
                    continue

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
                    report_md = str(data.get("report.md", ""))
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

                if status == "finish":
                    if report_md.strip():
                        final_report_md = report_md.strip()
                    log_success(logger, f"PwnAgent finished in round {round_idx}")
                    break

                messages.append({"role": "user", "content": "继续"})
        finally:
            (ctx.run_dir / "messages.json").write_text(
                json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            log_info(logger, f"Messages saved to: {ctx.run_dir / 'messages.json'}")

        report_path = ctx.run_dir / "report.md"
        if final_report_md:
            report_path.write_text(final_report_md, encoding="utf-8")
            log_success(logger, f"Report written to: {report_path}")
        else:
            log_error(logger, "PwnAgent failed: no report.md generated")
            raise RuntimeError("PwnAgent执行失败，没有生成report.md")

        log_section(logger, "✅ PwnAgent Completed Successfully")
