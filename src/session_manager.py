from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class AgentPhase(Enum):
    IDLE = "idle"
    PLAN = "plan"
    PWN = "pwn"
    FINISHED = "finished"


@dataclass
class SessionState:
    session_id: str
    project_root: str
    binary_path: str
    poc_md_path: Optional[str] = None
    plan_md_path: Optional[str] = None
    exp_path: Optional[str] = None

    phase: str = AgentPhase.IDLE.value
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    messages: List[Dict[str, Any]] = field(default_factory=list)

    plan_content: Optional[str] = None
    report_content: Optional[str] = None

    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        valid_fields = {
            "session_id", "project_root", "binary_path", "poc_md_path",
            "plan_md_path", "exp_path", "phase", "created_at", "updated_at",
            "messages", "step_results", "plan_content", "report_content", "error",
        }
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)

    def update_timestamp(self) -> None:
        self.updated_at = datetime.now().isoformat()


class SessionManager:
    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session(
            self,
            project_root: Path,
            binary_path: Path,
            poc_md_path: Optional[Path] = None,
            plan_md_path: Optional[Path] = None,
    ) -> SessionState:
        session_id = datetime.now().strftime("%y-%m-%d-%H-%M-%S")

        session = SessionState(
            session_id=session_id,
            project_root=str(project_root),
            binary_path=str(binary_path),
            poc_md_path=str(poc_md_path) if poc_md_path else None,
            plan_md_path=str(plan_md_path) if plan_md_path else None,
        )

        run_dir = self._get_run_dir(session_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        self.save_session(session)
        return session

    def load_session(self, session_id: str) -> Optional[SessionState]:
        session_file = self._get_session_file(session_id)
        if not session_file.exists():
            return None

        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            return SessionState.from_dict(data)
        except Exception:
            return None

    def save_session(self, session: SessionState) -> None:
        session.update_timestamp()
        session_file = self._get_session_file(session.session_id)
        session_file.write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def list_sessions(self, limit: int = 50) -> List[SessionState]:
        sessions: List[SessionState] = []

        for session_dir in sorted(
                self.sessions_dir.iterdir(),
                key=lambda x: x.stat().st_mtime,
                reverse=True
        ):
            if not session_dir.is_dir():
                continue

            session_file = session_dir / "session.json"
            if not session_file.exists():
                continue

            session = self.load_session(session_dir.name)
            if session:
                sessions.append(session)
                if len(sessions) >= limit:
                    break

        return sessions

    def delete_session(self, session_id: str) -> bool:
        run_dir = self._get_run_dir(session_id)
        if not run_dir.exists():
            return False

        import shutil
        shutil.rmtree(run_dir)
        return True

    def get_run_dir(self, session_id: str) -> Path:
        return self._get_run_dir(session_id)

    def _get_run_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def _get_session_file(self, session_id: str) -> Path:
        return self._get_run_dir(session_id) / "session.json"
