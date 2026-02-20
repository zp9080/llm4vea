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
from utils.logger import get_logger, log_llm_request, log_llm_response

logger = get_logger(__name__)


class PlanAgent(BaseAgent):
    """多轮 LLM 驱动的规划 Agent。

    设计要点：
    - 外部输入尽量简单：二进制路径 + info_md；
    - skills 作为高优先级“工具”，通过 <skills> 索引暴露 name/description，是否深入阅读由 LLM 自己决定；
    - 多轮循环由 LLM 通过 status 决定何时结束，我们只设置最大轮数上限防止死循环。"""

    def __init__(self, ctx: RunContext) -> None:
        super().__init__(ctx, name="PlanAgent")

    def run(self) -> None:  # type: ignore[override]
        ctx = self.ctx
        tools = ctx.tools
        binary = ctx.binary
        info_md = ctx.info_md
        llm = ctx.llm

        logger.info(f"PlanAgent started, binary: {binary}, info_md: {info_md}")

        skills_index = list_skills()
        tools_index = tools.list_tools()
        skill_for_plan = load_skill("core", "checksec") + load_skill("core", "rop-gadget")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        plan_path = ctx.run_dir / "plan.md"

        user_parts: List[str] = ["# Task\n", f"- binary_path: {binary}\n"]
        if info_md is not None:
            user_parts.append(f"- info_md_path: {info_md}\n")
        user_parts.append(f"- generated_at: {now}\n")

        if info_md is not None and info_md.exists():
            user_parts.append("\n## Input info markdown\n\n```markdown\n")
            user_parts.append(info_md.read_text(encoding="utf-8"))
            user_parts.append("\n```\n")

        user_base_context = "".join(user_parts)

        system_parts: List[str] = []
        if skill_for_plan:
            system_parts.append("\n# Important Skill For Plan\n")
            system_parts.append(skill_for_plan)

        system_parts.append("\n# Tools index\n")
        system_parts.append(tools_index)

        system_parts.append("\n# Skills index\n")
        system_parts.append(skills_index)

        system_base_context = "".join(system_parts)

        # 2. LLM 自主控制的多轮循环
        max_rounds = 10
        final_plan: str | None = None

        logger.info(f"Starting multi-round LLM loop, max rounds: {max_rounds}")

        messages = [
            {"role": "system", "content": PLAN_AGENT_SYSTEM_PROMPT + "\n\n" + SKILL_PROMPT + "\n\n" + system_base_context},
            {"role": "user", "content": user_base_context},
        ]

        for round_idx in range(1, max_rounds + 1):
            logger.info(f"Round {round_idx}/{max_rounds}")
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

            # 处理tool_calls
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

            # 处理返回的json数据
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
                plan_md = str(data.get("plan.md", ""))
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

            if status == "finish" and plan_md.strip():
                logger.info(f"PlanAgent finished in round {round_idx}")
                final_plan = plan_md.strip()
                break

            messages.append({"role": "user", "content": "继续"})

        # 3. 若多轮 LLM 没有给出最终 plan，则回退到本地拼接版本
        if final_plan is None:
            logger.error("PlanAgent failed: no final plan generated")
            raise RuntimeError("PlanAgent执行失败，没有返回plan.md")
        plan_path.write_text(final_plan, encoding="utf-8")
        logger.info(f"Plan written to: {plan_path}")
        (self.ctx.run_dir / "messages.json").write_text(
            json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"Messages saved to: {self.ctx.run_dir / 'messages.json'}")
        logger.info("PlanAgent completed successfully")
