from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.base_agent import RunContext
from agents.plan_agent import PlanAgent
from agents.pwn_agent import PwnAgent
from clients.llm_client import OpenAIClient
from tools.tool_registry import ToolRegistry
from workflows.pwn_graph import run_pwn_workflow
from utils.logger import get_logger

logger = get_logger(__name__)


def _project_root() -> Path:
    # src/main.py -> src -> project root
    return Path(__file__).resolve().parents[2]

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM-driven Pwn workflow runner (PlanAgent / PwnAgent).",
    )
    parser.add_argument(
        "-binary",
        required=True,
        help="目标二进制文件路径",
    )
    parser.add_argument(
        "-poc_md",
        help="Plan 阶段使用的poc.md",
    )
    parser.add_argument(
        "-plan_md",
        help="仅运行 Pwn 阶段时提供的 plan.md 路径；如果同时运行 Plan，则忽略此参数",
    )
    parser.add_argument(
        "-plan",
        action="store_true",
        help="只运行 Plan 阶段（不加任何参数时默认 Plan + Pwn 都运行）",
    )
    parser.add_argument(
        "-pwn",
        action="store_true",
        help="只运行 Pwn 阶段（不加任何参数时默认 Plan + Pwn 都运行）",
    )

    args = parser.parse_args()

    logger.info("Starting LLM-driven Pwn workflow runner")
    logger.info(f"Binary path: {args.binary}")
    logger.info(f"Poc md: {args.poc_md}")
    logger.info(f"Plan md: {args.plan_md}")
    logger.info(f"Run plan only: {args.plan}")
    logger.info(f"Run pwn only: {args.pwn}")

    # 默认同时运行 Plan 和 Pwn；只有显式指定时才选择单个阶段
    run_plan= True
    run_pwn = True
    if args.plan and not args.pwn:
        run_plan = True
        run_pwn = False
    if args.pwn and not args.plan:
        run_plan = False
        run_pwn = True

    logger.info(f"Will run plan: {run_plan}, will run pwn: {run_pwn}")

    project_root = _project_root()
    binary = Path(args.binary).resolve()
    logger.info(f"Project root: {project_root}")
    logger.info(f"Resolved binary path: {binary}")

    if run_plan and args.poc_md is None:
        parser.error("-poc_md 在运行 Plan 阶段时必需")
    poc_md_path = Path(args.info_md).resolve()
    logger.info(f"Resolved poc_md path: {poc_md_path}")

    # 情况 1：Plan + Pwn 一起跑，直接交给 LangGraph 工作流
    if run_plan and run_pwn:
        logger.info("Running Plan + Pwn workflow via LangGraph")
        state = run_pwn_workflow(project_root, binary, poc_md_path)
        if state.get("error"):
            logger.error(f"[pwn-workflow] error: {state['error']}")
        else:
            logger.info(f"[pwn-workflow] plan: {state.get('plan_md_path')}, exp: {state.get('exp_path')}")
        return

    run_id = datetime.now().strftime("%y-%m-%d-%H-%M-%S")
    run_dir = project_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Run ID: {run_id}, Run directory: {run_dir}")

    # 如果只运行 Pwn，没有 Plan，需要显式提供 plan.md
    ctx_plan_md: Optional[Path]
    if not run_plan and run_pwn:
        if args.plan_md is None:
            parser.error("仅运行 Pwn 阶段时必须通过 -plan_md 指定已有的 plan.md 路径")
        ctx_plan_md = Path(args.plan_md).resolve()
        logger.info(f"Using existing plan.md: {ctx_plan_md}")
    # 如果只运行 Plan，则在上下文中固定 plan.md 路径为 runs/{ts}/plan.md
    else:
        ctx_plan_md = run_dir / "plan.md"
        logger.info(f"Plan will be written to: {ctx_plan_md}")

    tools = ToolRegistry()

    llm = OpenAIClient.build()
    logger.info(f"LLM client initialized with model: {getattr(llm, 'model', 'unknown')}")

    ctx = RunContext(
        project_root=project_root,
        run_dir=run_dir,
        binary=binary,
        poc_md=poc_md_path,
        plan_md=ctx_plan_md,
        tools=tools,
        llm=llm
    )

    # 记录基本配置信息，便于后续分析
    config = {
        "run_id": run_id,
        "binary": str(binary),
        "poc_md": str(poc_md_path) if poc_md_path is not None else None,
        "plan_md": str(ctx_plan_md) if ctx_plan_md is not None else None,
        "run_plan": bool(run_plan),
        "run_pwn": bool(run_pwn),
        "llm_model": getattr(llm, "model", "unknown"),
    }
    (run_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Config written to: {run_dir / 'config.json'}")

    if run_plan:
        logger.info("Starting PlanAgent")
        plan_agent = PlanAgent(ctx)
        plan_agent.run()
        logger.info("PlanAgent completed")

    if run_pwn:
        logger.info("Starting PwnAgent")
        pwn_agent = PwnAgent(ctx)
        pwn_agent.run()
        logger.info("PwnAgent completed")

    logger.info("Workflow finished successfully")


if __name__ == "__main__":  # pragma: no cover
    main()
