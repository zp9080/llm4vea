import sys
from pathlib import Path

src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import streamlit as st
from typing import Optional
import json

from session_manager import SessionManager, SessionState, AgentPhase
from agents.interactive_agent import InteractivePwnAgent


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def init_session_state():
    if "session_manager" not in st.session_state:
        sessions_dir = _project_root() / "runs"
        st.session_state.session_manager = SessionManager(sessions_dir)

    if "current_session" not in st.session_state:
        st.session_state.current_session = None

    if "agent" not in st.session_state:
        st.session_state.agent = None

    if "processing" not in st.session_state:
        st.session_state.processing = False


def get_session_manager() -> SessionManager:
    return st.session_state.session_manager


def get_current_session() -> Optional[SessionState]:
    return st.session_state.current_session


def get_agent() -> Optional[InteractivePwnAgent]:
    return st.session_state.agent


def render_sidebar():
    st.sidebar.title("🎯 Pwn Agent")

    with st.sidebar.expander("📁 新建会话", expanded=True):
        with st.form("new_session_form"):
            binary_path = st.text_input(
                "Binary 路径",
                placeholder="/path/to/binary",
                help="目标二进制文件的绝对路径"
            )

            poc_md_path = st.text_input(
                "Poc.md 路径 (可选)",
                placeholder="/path/to/poc.md",
                help="漏洞描述文档路径"
            )

            plan_md_path = st.text_input(
                "Plan.md 路径 (可选)",
                placeholder="/path/to/plan.md",
                help="计划文档路径，用于 Pwn 阶段"
            )

            submitted = st.form_submit_button("🚀 创建会话", use_container_width=True)

            if submitted:
                if not binary_path.strip():
                    st.error("请输入 Binary 路径")
                elif not Path(binary_path).exists():
                    st.error("Binary 文件不存在")
                else:
                    poc_path = Path(poc_md_path) if poc_md_path.strip() else None
                    plan_path = Path(plan_md_path) if plan_md_path.strip() else None

                    if poc_path and not poc_path.exists():
                        st.error("Poc.md 文件不存在")
                    elif plan_path and not plan_path.exists():
                        st.error("Plan.md 文件不存在")
                    else:
                        session = get_session_manager().create_session(
                            project_root=_project_root(),
                            binary_path=Path(binary_path),
                            poc_md_path=poc_path,
                            plan_md_path=plan_path,
                        )
                        st.session_state.current_session = session
                        st.session_state.agent = InteractivePwnAgent(
                            session,
                            get_session_manager()
                        )
                        st.rerun()

    st.sidebar.divider()

    with st.sidebar.expander("📜 历史会话", expanded=True):
        sessions = get_session_manager().list_sessions(limit=20)

        if not sessions:
            st.info("暂无历史会话")
        else:
            for session in sessions:
                phase_emoji = {
                    AgentPhase.IDLE.value: "⚪",
                    AgentPhase.PLAN.value: "🔵",
                    AgentPhase.PWN.value: "🟡",
                    AgentPhase.FINISHED.value: "🟢",
                }.get(session.phase, "⚪")

                is_current = (st.session_state.current_session and
                              st.session_state.current_session.session_id == session.session_id)

                col1, col2 = st.columns([4, 1])

                with col1:
                    btn_type = "primary" if is_current else "secondary"
                    if st.button(
                            f"{phase_emoji} {session.session_id[:8]}...",
                            key=f"session_{session.session_id}",
                            use_container_width=True,
                            type=btn_type,
                    ):
                        st.session_state.current_session = session
                        st.session_state.agent = InteractivePwnAgent(
                            session,
                            get_session_manager()
                        )
                        st.rerun()

                with col2:
                    if st.button("🗑️", key=f"delete_{session.session_id}", help="删除会话"):
                        get_session_manager().delete_session(session.session_id)
                        if is_current:
                            st.session_state.current_session = None
                            st.session_state.agent = None
                        st.rerun()

                st.caption(f"Binary: {Path(session.binary_path).name}")


def render_user_message(msg: dict):
    content = msg.get("content", "")
    if content:
        expanded = len(content) < 1000
        with st.expander("👤 用户消息", expanded=expanded):
            st.markdown(content)


def render_assistant_message(msg: dict):
    content = msg.get("content", "")
    if content:
        expanded = len(content) < 1000
        with st.expander("🤖 助手消息", expanded=expanded):
            st.markdown(content)


def render_tool_message(msg: dict):
    content = msg.get("content", "")

    try:
        data = json.loads(content)
        tool_name = data.get("name", "Unknown")
        args = data.get("args", {})
        returncode = data.get("returncode", -1)
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        metadata = data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {}
    except (json.JSONDecodeError, TypeError):
        tool_name = "Unknown"
        args = {}
        returncode = -1
        stdout = content
        stderr = ""
        metadata = {}

    is_success = returncode == 0
    status_icon = "✅" if is_success else "❌"

    tool_kind = str(metadata.get("tool_kind", "tool"))
    if tool_kind == "mcp":
        mcp_server = str(metadata.get("mcp_server", "")).strip()
        mcp_tool = str(metadata.get("mcp_tool", "")).strip()
        display_name = mcp_tool or tool_name
        prefix = f"🛰️ MCP {mcp_server}:" if mcp_server else "🛰️ MCP"
        header = f"**{prefix}{display_name}** {status_icon}"
    else:
        header = f"**🔧 {tool_name}** {status_icon}"

    with st.container(border=True):
        st.markdown(header)

        if args:
            with st.expander("📋 参数", expanded=False):
                st.json(args)

        structured = metadata.get("structuredContent")
        if structured is not None:
            with st.expander("🧩 structuredContent", expanded=False):
                st.json(structured)

        if stdout.strip():
            with st.expander("📤 stdout", expanded=False):
                st.code(stdout, language="text")

        if stderr.strip():
            with st.expander("📥 stderr", expanded=False):
                st.code(stderr, language="text")


def render_chat_message(msg: dict):
    role = msg.get("role", "unknown")

    if role == "system":
        return
    elif role == "user":
        with st.chat_message("user"):
            render_user_message(msg)
    elif role == "assistant":
        with st.chat_message("assistant"):
            render_assistant_message(msg)
    elif role == "tool":
        with st.chat_message("assistant"):
            render_tool_message(msg)


def render_chat_interface():
    session = get_current_session()
    agent = get_agent()

    if not session or not agent:
        st.info("👈 请在左侧创建或选择一个会话")
        return

    col1, col2, col3 = st.columns([2, 2, 1])
    phase_display = {
        AgentPhase.IDLE.value: "⚪ 空闲",
        AgentPhase.PLAN.value: "🔵 Plan 阶段",
        AgentPhase.PWN.value: "🟡 Pwn 阶段",
        AgentPhase.FINISHED.value: "🟢 已完成",
    }.get(session.phase, session.phase)

    with col1:
        st.subheader(f"**会话:** `{session.session_id}`")
    with col2:
        st.subheader(f"**阶段:** {phase_display}")
    with col3:
        if st.button("🔄 重置", use_container_width=True):
            agent.reset_phase()
            st.session_state.processing = False
            st.rerun()

    st.divider()

    col_info1, col_info2 = st.columns([3, 1])
    with col_info1:
        st.markdown(f"**Binary:** `{Path(session.binary_path)}`")
        if session.poc_md_path:
            st.markdown(f"**Poc.md:** `{Path(session.poc_md_path)}`")
        if session.plan_md_path:
            st.markdown(f"**Plan.md:** `{Path(session.plan_md_path)}`")

    with col_info2:
        if "max_steps" not in st.session_state:
            st.session_state.max_steps = 15
        max_steps = st.selectbox(
            "最大轮次",
            options=[5, 10, 15, 20, 25, 30],
            index=[5, 10, 15, 20, 25, 30].index(st.session_state.max_steps),
            key="max_steps_select",
        )
        st.session_state.max_steps = max_steps

    col_phase1, col_phase2 = st.columns([1, 1])
    with col_phase1:
        if st.button("🔵 切换到 Plan", use_container_width=True, disabled=(session.phase == AgentPhase.PLAN.value)):
            agent.switch_phase(AgentPhase.PLAN.value)
            st.session_state.processing = False
            st.rerun()
    with col_phase2:
        if st.button("🟡 切换到 Pwn", use_container_width=True, disabled=(session.phase == AgentPhase.PWN.value)):
            agent.switch_phase(AgentPhase.PWN.value)
            st.session_state.processing = False
            st.rerun()

    st.divider()

    st.subheader("💬 对话")

    chat_container = st.container()

    with chat_container:
        for msg in session.messages:
            render_chat_message(msg)

    if st.session_state.processing:
        st.warning("⏳ Agent 正在处理... 如果已停止，请点击上方的「🔄 重置状态」按钮")

    st.divider()

    if session.phase != AgentPhase.FINISHED.value:
        user_input = st.chat_input("输入消息...")

        if user_input and not st.session_state.processing:
            st.session_state.processing = True

            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                with st.spinner("处理中..."):
                    try:
                        agent.process_user_message(user_input, max_steps=st.session_state.max_steps)
                    except Exception as e:
                        st.error(f"处理失败: {e}")

                st.session_state.current_session = get_session_manager().load_session(
                    session.session_id
                )

            st.session_state.processing = False
            st.rerun()
    else:
        st.info("🎉 会话已完成，如需继续请重置或创建新会话")


def render_files_panel():
    session = get_current_session()

    if not session:
        return

    st.sidebar.divider()

    with st.sidebar.container():
        st.markdown("**📂 文件**")

        run_dir = get_session_manager().get_run_dir(session.session_id)

        plan_md = run_dir / "plan.md"
        if plan_md.exists():
            with st.sidebar.expander("📄 plan.md"):
                st.markdown(plan_md.read_text(encoding="utf-8"))

        exp_py = run_dir / "exp.py"
        if exp_py.exists():
            with st.sidebar.expander("🐍 exp.py"):
                st.code(exp_py.read_text(encoding="utf-8"), language="python")

        report_md = run_dir / "report.md"
        if report_md.exists():
            with st.sidebar.expander("📄 report.md"):
                st.markdown(report_md.read_text(encoding="utf-8"))


def main():
    st.set_page_config(
        page_title="Pwn Agent",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("🎯 LLM-driven Pwn Agent")

    init_session_state()

    render_sidebar()
    render_files_panel()
    render_chat_interface()


if __name__ == "__main__":
    main()
