from __future__ import annotations

import json
from pathlib import Path
from typing import List

from agents.base_agent import BaseAgent, RunContext
from tools.tool_registry import ToolResult
from skills.skill_loader import load_skill, list_skills
from agents.prompts import PWN_AGENT_SYSTEM_PROMPT, SKILL_PROMPT
from utils.logger import get_logger, log_llm_request, log_llm_response

logger = get_logger(__name__)


class PwnAgent(BaseAgent):
    """多轮 LLM 驱动的 EXP 生成 Agent。

    设计要点：
    - 每一轮由 LLM 决定是继续迭代(`status=continue`)还是结束(`status=finish`)；
    - 框架在每轮后执行 exp-runner，将 stdout/stderr 摘要作为下一轮的调试信号；
    - 设定最大轮数上限（如 10）防止死循环。"""

    def __init__(self, ctx: RunContext) -> None:
        super().__init__(ctx, name="PwnAgent")

    def run(self) -> None:  # type: ignore[override]
        ctx = self.ctx
        binary = ctx.binary
        tools = ctx.tools
        plan_md = ctx.plan_md
        llm = ctx.llm

        exp_py = ctx.run_dir / "exp.py"

        logger.info(f"PwnAgent started, binary: {binary}, plan_md: {plan_md}")

        plan_text = ""
        if plan_md is not None and Path(plan_md).exists():
            plan_text = Path(plan_md).read_text(encoding="utf-8")
            logger.info(f"Loaded plan from {plan_md}")

        skill_for_pwn = load_skill("core", "pwndbg") + load_skill("core", "pwntools")
        skills_index = list_skills()
        tools_index = tools.list_tools()

        user_parts: List[str] = []
        user_parts.append(f"# Task\n- binary_path: {binary}\n")
        if plan_text:
            user_parts.append("\n# plan.md\n\n" + plan_text + "\n")
        user_base_context = "".join(user_parts)

        system_parts: List[str] = []
        if skill_for_pwn:
            system_parts.append("\n# Important Skill For Pwn\n")
            system_parts.append(skill_for_pwn)
        system_parts.append("\n# Tools index\n")
        system_parts.append(tools_index)
        system_parts.append("\n# Skills index\n")
        system_parts.append(skills_index)
        system_base_context = "".join(system_parts)

        max_rounds = 20
        last_result: ToolResult | None = None
        last_code: str | None = None
        final_debug_md: str | None = None
        final_report_md: str | None = None

        logger.info(f"Starting multi-round LLM loop, max rounds: {max_rounds}")

        messages = [
            {"role": "system", "content": PWN_AGENT_SYSTEM_PROMPT + "\n\n" + SKILL_PROMPT + "\n\n" + system_base_context},
            {"role": "user", "content": user_base_context},
        ]

        for round_idx in range(1, max_rounds + 1):
            logger.info(f"Round {round_idx}/{max_rounds}")
            if last_code is not None and last_result is not None:
                debug_parts: List[str] = []
                debug_parts.append("\n# 上一轮的 exp.py\n\n```python\n")
                debug_parts.append(last_code)
                debug_parts.append("\n```\n")
                debug_parts.append("\n# 上一轮运行的调试输出 (stdout/stderr 摘要)\n\n```text\n")
                debug_snippet = (last_result.stdout + "\n" + last_result.stderr)
                debug_parts.append(debug_snippet)
                debug_parts.append("\n```\n")
                messages.append({"role": "user", "content": "".join(debug_parts)})
                logger.debug(f"Added debug output from previous round to messages")

            try:
                log_llm_request(logger, messages, tools=tools.schemas)
                resp = llm.complete(messages, tools=tools.schemas)
                log_llm_response(logger, resp)
            except Exception as exc:
                logger.error(f"Failed to complete plan in round {round_idx}: {exc}")
                raise RuntimeError(f"Failed to complete plan: {exc}") from exc

            if not isinstance(resp, dict):
                raise RuntimeError(f"response is not a dict: {resp}")

            messages.append(resp)

            tool_calls = resp.get("tool_calls", None)
            if isinstance(tool_calls, list) and tool_calls:
                logger.info(f"Received {len(tool_calls)} tool calls in round {round_idx}")
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
                    logger.debug(f"Executing tool: {name} with args: {args}")
                    result: ToolResult = tools.run(name, **args)
                    logger.debug(f"Tool {name} completed with returncode: {result.returncode}")
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

            raw = resp.get("content", "")
            if not isinstance(raw, str) or not raw.strip():
                logger.warning(f"Empty response in round {round_idx}")
                break

            try:
                data = json.loads(raw)
            except Exception:
                logger.warning(f"Invalid JSON response in round {round_idx}: {raw[:100]}...")
                messages.append({"role": "user", "content": "返回的内容不是纯json，请重新返回"})
                continue

            try:
                status = str(data.get("status", "")).lower()
                exp_code = str(data.get("exp.py", ""))
                debug_md = str(data.get("debug.md", ""))
                report_md = str(data.get("report.md", ""))
                think = str(data.get("think", ""))
            except Exception as e:
                logger.error(f"Failed to parse JSON fields in round {round_idx}: {e}")
                messages.append({"role": "user", "content": f"返回的json字段解析失败: {e}，请重新返回"})
                continue

            if status not in {"continue", "finish"}:
                logger.warning(f"Invalid status '{status}' in round {round_idx}")
                messages.append({"role": "user", "content": "返回的status应当是continue或finish两者状态之一，继续分析任务"})
                continue

            logger.info(f"Round {round_idx} status: {status}")
            if think.strip():
                logger.debug(f"Round {round_idx} think: {think[:100]}...")
                messages.append({"role": "assistant", "content": f"[Think] {think.strip()}"})

            if exp_code.strip():
                last_code = exp_code.strip()
                exp_py.write_text(last_code, encoding="utf-8")
                logger.info(f"Exp written to: {exp_py}")
                result = tools.run("exp_runner", script_path=str(exp_py), cwd=binary.parent)
                last_result = result
                logger.info(f"Exp runner executed with returncode: {result.returncode}")

            if status == "finish":
                if debug_md.strip():
                    final_debug_md = debug_md.strip()
                if report_md.strip():
                    final_report_md = report_md.strip()
                logger.info(f"PwnAgent finished in round {round_idx}")
                break

            messages.append({"role": "user", "content": "继续"})

        if last_code is None:
            logger.error("PwnAgent failed: no exp.py generated")
            raise RuntimeError("PwnAgent执行失败，没有生成exp.py")

        report_path = ctx.run_dir / "report.md"
        debug_path = ctx.run_dir / "debug.md"

        if final_report_md:
            report_path.write_text(final_report_md, encoding="utf-8")
            logger.info(f"Report written to: {report_path}")
        else:
            logger.error("PwnAgent failed: no report.md generated")
            raise RuntimeError("PwnAgent执行失败，没有生成report.md")

        if final_debug_md:
            debug_path.write_text(final_debug_md, encoding="utf-8")
            logger.info(f"Debug written to: {debug_path}")
        else:
            logger.error("PwnAgent failed: no debug.md generated")
            raise RuntimeError("PwnAgent执行失败，没有生成debug.md")

        (ctx.run_dir / "messages.json").write_text(
            json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"Messages saved to: {ctx.run_dir / 'messages.json'}")
        logger.info("PwnAgent completed successfully")
