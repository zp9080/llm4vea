import sys
from pathlib import Path

src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import streamlit as st
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

from session_manager import SessionManager, SessionState, AgentPhase
from interactive_agent import InteractivePwnAgent, StepResult


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
    
    if "step_results" not in st.session_state:
        st.session_state.step_results = []


def get_session_manager() -> SessionManager:
    return st.session_state.session_manager


def get_current_session() -> Optional[SessionState]:
    return st.session_state.current_session


def get_agent() -> Optional[InteractivePwnAgent]:
    return st.session_state.agent


def render_sidebar():
    st.sidebar.title("🎯 Pwn Agent")
    st.sidebar.markdown("---")
    
    st.sidebar.subheader("📁 新建会话")
    
    with st.sidebar.form("new_session_form"):
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
        
        submitted = st.form_submit_button("🚀 创建会话", use_container_width=True)
        
        if submitted:
            if not binary_path.strip():
                st.sidebar.error("请输入 Binary 路径")
            elif not Path(binary_path).exists():
                st.sidebar.error("Binary 文件不存在")
            else:
                poc_path = Path(poc_md_path) if poc_md_path.strip() else None
                if poc_path and not poc_path.exists():
                    st.sidebar.error("Poc.md 文件不存在")
                else:
                    session = get_session_manager().create_session(
                        project_root=_project_root(),
                        binary_path=Path(binary_path),
                        poc_md_path=poc_path,
                    )
                    st.session_state.current_session = session
                    st.session_state.agent = InteractivePwnAgent(
                        session, 
                        get_session_manager()
                    )
                    st.session_state.step_results = []
                    st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("📜 历史会话")
    
    sessions = get_session_manager().list_sessions(limit=20)
    
    for session in sessions:
        col1, col2 = st.sidebar.columns([3, 1])
        
        phase_emoji = {
            AgentPhase.IDLE.value: "⚪",
            AgentPhase.PLAN.value: "🔵",
            AgentPhase.PWN.value: "🟡",
            AgentPhase.FINISHED.value: "🟢",
        }.get(session.phase, "⚪")
        
        with col1:
            if st.button(
                f"{phase_emoji} {session.session_id}",
                key=f"session_{session.session_id}",
                use_container_width=True,
            ):
                st.session_state.current_session = session
                st.session_state.agent = InteractivePwnAgent(
                    session,
                    get_session_manager()
                )
                st.session_state.step_results = []
                st.rerun()
        
        with col2:
            if st.button("🗑️", key=f"delete_{session.session_id}"):
                get_session_manager().delete_session(session.session_id)
                if (st.session_state.current_session and 
                    st.session_state.current_session.session_id == session.session_id):
                    st.session_state.current_session = None
                    st.session_state.agent = None
                st.rerun()
        
        st.sidebar.caption(f"Binary: {Path(session.binary_path)}")


def render_chat_message(role: str, content: str):
    with st.chat_message(role):
        st.markdown(content)


def render_step_result(result: StepResult):
    if result.step_type == "think":
        with st.expander("💭 思考过程", expanded=False):
            st.markdown(result.content)
    
    elif result.step_type == "tool_call":
        st.info(f"🔧 调用工具: **{result.tool_name}**")
        if result.tool_args:
            with st.expander("参数", expanded=False):
                st.json(result.tool_args)
    
    elif result.step_type == "tool_result":
        returncode = result.tool_result.returncode
        success = returncode == 0
        
        icon = "✅" if success else "❌"
        with st.expander(
            f"{icon} 工具结果: {result.tool_name} (exit: {returncode})",
            expanded=not success
        ):
            if result.tool_result.stdout:
                st.subheader("stdout")
                st.code(result.tool_result.stdout, language="text")
            if result.tool_result.stderr:
                st.subheader("stderr")
                st.code(result.tool_result.stderr, language="text")
    
    elif result.step_type == "plan_complete":
        st.success("✅ Plan 生成完成!")
        with st.expander("📄 Plan.md", expanded=True):
            st.markdown(result.content)
    
    elif result.step_type == "report_complete":
        st.success("✅ Report 生成完成!")
        with st.expander("📄 Report.md", expanded=True):
            st.markdown(result.content)
    
    elif result.step_type == "phase_change":
        st.info(f"🔄 {result.content}")
    
    elif result.step_type == "finished":
        st.success("🎉 " + result.content)
    
    elif result.step_type == "error":
        st.error(f"❌ 错误: {result.error}")
    
    elif result.step_type == "message":
        st.markdown(result.content)


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
            st.session_state.step_results = []
            st.rerun()
    
    st.markdown("---")
    
    col_info1, col_info2 = st.columns([3, 1])
    with col_info1:
        st.markdown(f"**Binary:** `{Path(session.binary_path)}`")
        if session.poc_md_path:
            st.markdown(f"**Poc.md:** `{Path(session.poc_md_path)}`")
    
    with col_info2:
        if "max_steps" not in st.session_state:
            st.session_state.max_steps = 15
        max_steps = st.selectbox(
            "最大轮次",
            options=[10, 15, 20, 25, 30],
            index=[10, 15, 20, 25, 30].index(st.session_state.max_steps),
            key="max_steps_select",
        )
        st.session_state.max_steps = max_steps
    
    col_phase1, col_phase2, col_phase3 = st.columns([1, 1, 2])
    with col_phase1:
        if st.button("🔵 切换到 Plan", use_container_width=True, disabled=(session.phase == AgentPhase.PLAN.value)):
            agent.switch_phase(AgentPhase.PLAN.value)
            st.session_state.step_results = []
            st.rerun()
    with col_phase2:
        if st.button("🟡 切换到 Pwn", use_container_width=True, disabled=(session.phase == AgentPhase.PWN.value)):
            agent.switch_phase(AgentPhase.PWN.value)
            st.session_state.step_results = []
            st.rerun()
    
    st.markdown("---")
    
    st.subheader("💬 对话")
    
    chat_container = st.container()
    
    with chat_container:
        for msg in session.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            if role == "system":
                continue
            elif role == "user":
                with st.chat_message("user"):
                    st.markdown(content)
            elif role == "assistant":
                with st.chat_message("assistant"):
                    st.markdown(content)
            elif role == "tool":
                continue
        
        for result in st.session_state.step_results:
            render_step_result(result)
    
    if st.session_state.processing:
        st.info("⏳ Agent 正在处理...")
    
    st.markdown("---")
    
    if session.phase != AgentPhase.FINISHED.value:
        user_input = st.chat_input("输入消息...")
        
        if user_input and not st.session_state.processing:
            st.session_state.processing = True
            st.session_state.step_results = []
            
            with st.chat_message("user"):
                st.markdown(user_input)
            
            with st.chat_message("assistant"):
                progress_bar = st.progress(0, text="处理中...")
                
                step_results = []
                try:
                    for i, result in enumerate(agent.process_user_message(user_input, max_steps=st.session_state.max_steps)):
                        step_results.append(result)
                        render_step_result(result)
                        progress_bar.progress(
                            min(100, (i + 1) * 10),
                            text=f"步骤 {i + 1}: {result.step_type}"
                        )
                except Exception as e:
                    st.error(f"处理失败: {e}")
                finally:
                    progress_bar.empty()
                
                st.session_state.step_results = step_results
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
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("📂 文件")
    
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
    
    messages_json = run_dir / "messages.json"
    if messages_json.exists():
        with st.sidebar.expander("📋 messages.json"):
            try:
                data = json.loads(messages_json.read_text(encoding="utf-8"))
                st.json(data)
            except Exception:
                st.code(messages_json.read_text(encoding="utf-8"))


def main():
    st.set_page_config(
        page_title="Pwn Agent",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("🎯 LLM-driven Pwn Agent")
    st.markdown("基于 LLM 的多轮对话式 Pwn 漏洞利用生成工具")
    
    init_session_state()
    
    render_sidebar()
    render_files_panel()
    render_chat_interface()


if __name__ == "__main__":
    main()
