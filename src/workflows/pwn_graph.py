from __future__ import annotations

from typing import Any, Optional, TypedDict
from pathlib import Path
from datetime import datetime

from langgraph.graph import StateGraph, END

from agents.plan_agent import PlanAgent
from agents.pwn_agent import PwnAgent
from agents.base_agent import RunContext
from clients.llm_client import OpenAIClient
from tools.tool_registry import ToolRegistry
from utils.logger import get_logger

logger = get_logger(__name__)


class PwnState(TypedDict):
    """LangGraph 工作流使用的全局状态（精简版）。"""

    run_id: str
    project_root: str

    binary_path: str
    info_md_path: Optional[str]

    plan_md_path: Optional[str]
    exp_path: Optional[str]

    error: Optional[str]


def _build_run_context(state: PwnState) -> RunContext:
    """基于当前 state 构造一次运行的 RunContext。"""

    project_root = Path(state["project_root"]).resolve()
    run_dir = project_root / "runs" / state["run_id"]
    binary = Path(state["binary_path"]).resolve()

    info_md_path: Optional[Path]
    if state.get("info_md_path"):
        info_md_path = Path(state["info_md_path"]).resolve()
    else:
        info_md_path = None

    # 如果 state 已经给出 plan_md_path，则沿用；否则默认放在 run_dir 下
    if state.get("plan_md_path"):
        plan_md = Path(state["plan_md_path"]).resolve()
    else:
        plan_md = run_dir / "plan.md"

    tools = ToolRegistry()
    llm = OpenAIClient.build()

    return RunContext(
        project_root=project_root,
        run_dir=run_dir,
        binary=binary,
        info_md=info_md_path,
        plan_md=plan_md,
        tools=tools,
        llm=llm
    )


def plan_node(state: PwnState) -> PwnState:
    """调用现有 PlanAgent，生成 plan.md。"""

    logger.info(f"Plan node started with run_id: {state['run_id']}")
    ctx = _build_run_context(state)
    agent = PlanAgent(ctx)
    try:
        agent.run()
    except Exception as exc:  # 不中断整个 Graph，将错误写回状态
        logger.error(f"PlanAgent error: {exc}")
        new_state: PwnState = dict(state)
        new_state["error"] = f"PlanAgent error: {exc}"
        return new_state

    plan_path = ctx.plan_md or (ctx.run_dir / "plan.md")
    new_state = dict(state)
    new_state["plan_md_path"] = str(plan_path)
    logger.info(f"Plan node completed, plan written to: {plan_path}")
    return new_state  # 下一步由 Graph 路由到 Pwn 节点


def pwn_node(state: PwnState) -> PwnState:
    """调用现有 PwnAgent，基于 plan.md 生成 exp.py 并尝试运行。"""

    logger.info(f"Pwn node started with run_id: {state['run_id']}")
    # 确保 Pwn 阶段能看到 plan.md
    ctx = _build_run_context(state)
    if state.get("plan_md_path"):
        ctx.plan_md = Path(state["plan_md_path"]).resolve()
        logger.info(f"Using plan from: {ctx.plan_md}")

    agent = PwnAgent(ctx)
    try:
        agent.run()
    except Exception as exc:
        logger.error(f"PwnAgent error: {exc}")
        new_state: PwnState = dict(state)
        new_state["error"] = f"PwnAgent error: {exc}"
        return new_state

    # 目前 PwnAgent 固定把 EXP 写在 run_dir/exp.py
    exp_path = ctx.run_dir / "exp.py"
    new_state = dict(state)
    new_state["exp_path"] = str(exp_path)
    logger.info(f"Pwn node completed, exp written to: {exp_path}")
    return new_state


def build_pwn_graph() -> Any:
    """构建并返回编译后的 LangGraph Graph。

    目前是最简单的链式结构：PLAN -> PWN -> END，后续可以在此基础上
    增加循环、分支、多 Agent 等更复杂编排。"""

    graph = StateGraph(PwnState)
    graph.add_node("plan", plan_node)
    graph.add_node("pwn", pwn_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "pwn")
    graph.add_edge("pwn", END)

    return graph.compile()


def run_pwn_workflow(project_root: Path, binary: Path, info_md: Optional[Path] = None) -> PwnState:
    """外部入口：给定项目根目录、二进制路径和可选 info.md，跑完整个工作流。

    - 会自动创建 runs/{run_id}/ 目录
    - 会调用 PlanAgent 生成 plan.md，再调用 PwnAgent 生成 exp.py
    - 返回最终的 PwnState，包含 plan/exp 路径及 error 信息（如有）
    """

    run_id = datetime.now().strftime("%y-%m-%d-%H-%M-%S")
    logger.info(f"Starting pwn workflow with run_id: {run_id}")
    logger.info(f"Binary: {binary}, Info md: {info_md}")

    state: PwnState = {
        "run_id": run_id,
        "project_root": str(project_root.resolve()),
        "binary_path": str(binary.resolve()),
        "info_md_path": str(info_md.resolve()) if info_md is not None else None,
        "plan_md_path": None,
        "exp_path": None,
        "error": None,
    }

    # 确保 run 目录存在
    run_dir = project_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Run directory created: {run_dir}")

    graph = build_pwn_graph()
    final_state: PwnState = graph.invoke(state)

    if final_state.get("error"):
        logger.error(f"Workflow completed with error: {final_state['error']}")
    else:
        logger.info("Workflow completed successfully")
        logger.info(f"Final plan: {final_state.get('plan_md_path')}, Final exp: {final_state.get('exp_path')}")

    return final_state
