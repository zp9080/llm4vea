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
        "-info_md",
        help="Plan 阶段使用的补充信息 markdown（例如 PoC 说明）",
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

    # 默认同时运行 Plan 和 Pwn；只有显式指定时才选择单个阶段
    run_plan= True
    run_pwn = True
    if args.plan and not args.pwn:
        run_plan = True
        run_pwn = False
    if args.pwn and not args.plan:
        run_plan = False
        run_pwn = True

    project_root = _project_root()
    binary = Path(args.binary).resolve()
    if run_plan and args.info_md is None:
        parser.error("--info-md 在运行 Plan 阶段时必需（Plan 输入为二进制 + 补充信息 markdown）")
    info_md_path = Path(args.info_md).resolve()

    # 情况 1：Plan + Pwn 一起跑，直接交给 LangGraph 工作流
    if run_plan and run_pwn:
        state = run_pwn_workflow(project_root, binary, info_md_path)
        if state.get("error"):
            print(f"[pwn-workflow] error: {state['error']}")
        else:
            print(f"[pwn-workflow] plan: {state.get('plan_md_path')}, exp: {state.get('exp_path')}")
        return

    run_id = datetime.now().strftime("%y-%m-%d-%H-%M-%S")
    run_dir = project_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 如果只运行 Pwn，没有 Plan，需要显式提供 plan.md
    ctx_plan_md: Optional[Path]
    if not run_plan and run_pwn:
        if args.plan_md is None:
            parser.error("仅运行 Pwn 阶段时必须通过 --plan-md 指定已有的 plan.md 路径")
        ctx_plan_md = Path(args.plan_md).resolve()
    # 如果只运行 Plan，则在上下文中固定 plan.md 路径为 runs/{ts}/plan.md
    else:
        ctx_plan_md = run_dir / "plan.md"

    tools = ToolRegistry()

    llm = OpenAIClient.build()

    ctx = RunContext(
        project_root=project_root,
        run_dir=run_dir,
        binary=binary,
        info_md=info_md_path,
        plan_md=ctx_plan_md,
        tools=tools,
        llm=llm
    )

    # 记录基本配置信息，便于后续分析
    config = {
        "run_id": run_id,
        "binary": str(binary),
        "info_md": str(info_md_path) if info_md_path is not None else None,
        "plan_md": str(ctx_plan_md) if ctx_plan_md is not None else None,
        "run_plan": bool(run_plan),
        "run_pwn": bool(run_pwn),
        "llm_model": getattr(llm, "model", "unknown"),
    }
    (run_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    if run_plan:
        plan_agent = PlanAgent(ctx)
        plan_agent.run()

    if run_pwn:
        pwn_agent = PwnAgent(ctx)
        pwn_agent.run()


if __name__ == "__main__":  # pragma: no cover
    main()
