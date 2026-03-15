from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import json
import subprocess
import os
import signal


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_JSON = PROJECT_ROOT / "inputs" / "tools.json"


@dataclass
class ToolResult:
    name: str
    args: Dict[str, Any]
    stdout: str
    stderr: str
    returncode: int
    metadata: Dict[str, Any] | None = None


def _cleanup_gdb_processes():
    try:
        subprocess.run(["pkill", "-9", "gdb"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _run_subprocess(
    *,
    name: str,
    argv: List[str],
    args: Dict[str, Any],
    cwd: Optional[Path] = None,
    timeout: Optional[float] = None,
    env: Optional[Dict[str, str]] = None,
) -> ToolResult:
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
        )
        return ToolResult(
            name=name,
            args=args,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
            metadata={},
        )
    except subprocess.TimeoutExpired as exc:
        stdout_str = exc.stdout.decode('utf-8', errors='ignore') if exc.stdout else ""
        stderr_str = exc.stderr.decode('utf-8', errors='ignore') if exc.stderr else ""
        return ToolResult(
            name=name,
            args=args,
            stdout=stdout_str,
            stderr=stderr_str,
            returncode=-1,
            metadata={"timeout": True},
        )
    except FileNotFoundError as exc:
        return ToolResult(
            name=name,
            args=args,
            stdout="",
            stderr=str(exc),
            returncode=-127,
            metadata={"error": "command-not-found"},
        )


def bash_execute(*, command: str, cwd: str | Path | None = None, timeout: float | None = 60.0) -> ToolResult:
    run_cwd = Path(cwd).expanduser().resolve() if cwd is not None else None
    argv = ["bash", "-lc", command]
    return _run_subprocess(
        name="bash_execute",
        argv=argv,
        args={"command": command, "argv": argv, "cwd": str(run_cwd) if run_cwd is not None else None, "timeout": timeout},
        cwd=run_cwd,
        timeout=timeout,
        env=None,
    )


def grep_search(
    *,
    pattern: str,
    path: str | Path = ".",
    glob: str | None = None,
    ignore_case: bool = False,
    max_results: int = 200,
) -> ToolResult:
    search_path = str(path)
    argv: List[str] = ["rg", "--no-heading", "--color", "never", "-n"]
    if ignore_case:
        argv.append("-i")
    if glob:
        argv.extend(["--glob", glob])
    if max_results > 0:
        argv.extend(["--max-count", str(max_results)])
    argv.extend([pattern, search_path])
    return _run_subprocess(
        name="grep_search",
        argv=argv,
        args={
            "pattern": pattern,
            "path": search_path,
            "glob": glob,
            "ignore_case": ignore_case,
            "max_results": max_results,
            "argv": argv,
        },
        cwd=None,
        timeout=30.0,
        env=None,
    )


def list_dir(*, path: str | Path, recursive: bool = False, max_entries: int = 500) -> ToolResult:
    base = Path(path).expanduser().resolve()
    args = {"path": str(base), "recursive": recursive, "max_entries": max_entries}
    if not base.exists():
        return ToolResult(name="list_dir", args=args, stdout="", stderr=f"not found: {base}", returncode=1, metadata={})
    if not base.is_dir():
        return ToolResult(name="list_dir", args=args, stdout="", stderr=f"not a directory: {base}", returncode=1, metadata={})

    items: List[str] = []
    if recursive:
        for p in base.rglob("*"):
            items.append(str(p))
            if max_entries > 0 and len(items) >= max_entries:
                break
    else:
        for p in sorted(base.iterdir()):
            items.append(str(p))
            if max_entries > 0 and len(items) >= max_entries:
                break
    return ToolResult(name="list_dir", args=args, stdout="\n".join(items) + ("\n" if items else ""), stderr="", returncode=0, metadata={})


def file_read(*, path: str | Path, start_line: int = 1, limit: int = 200) -> ToolResult:
    file_path = Path(path).expanduser().resolve()
    args = {"path": str(file_path), "start_line": start_line, "limit": limit}
    if not file_path.exists():
        return ToolResult(name="file_read", args=args, stdout="", stderr=f"not found: {file_path}", returncode=1, metadata={})
    if not file_path.is_file():
        return ToolResult(name="file_read", args=args, stdout="", stderr=f"not a file: {file_path}", returncode=1, metadata={})

    if start_line < 1:
        start_line = 1
    if limit < 1:
        limit = 1

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start_idx = start_line - 1
    end_idx = min(len(lines), start_idx + limit)
    out_lines: List[str] = []
    width = len(str(end_idx if end_idx > 0 else 1))
    for i in range(start_idx, end_idx):
        out_lines.append(f"{str(i + 1).rjust(width)}\t{lines[i]}")
    return ToolResult(
        name="file_read",
        args=args,
        stdout="\n".join(out_lines) + ("\n" if out_lines else ""),
        stderr="",
        returncode=0,
        metadata={"total_lines": len(lines)},
    )

def file_write(*, path: str | Path, content: str, mode: str = "write") -> ToolResult:
    file_path = Path(path).expanduser().resolve()
    args = {"path": str(file_path), "content": content, "mode": mode}
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with open(file_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(content)
        else:
            file_path.write_text(content, encoding="utf-8", errors="replace")
        return ToolResult(
            name="file_write",
            args=args,
            stdout=f"written {len(content)} bytes to {file_path}",
            stderr="",
            returncode=0,
            metadata={"bytes_written": len(content)},
        )
    except Exception as exc:
        return ToolResult(
            name="file_write",
            args=args,
            stdout="",
            stderr=f"failed to write file: {exc}",
            returncode=1,
            metadata={"error": "write-failed"},
        )


def checksec(*, binary: str | Path) -> ToolResult:
    bin_path = str(binary)
    args = {"binary": bin_path}
    argv: List[str] = [
        "checksec", "--file", bin_path
    ]
    result = _run_subprocess(
            name="checksec",
            argv=argv,
            args={"binary": bin_path, "argv": argv},
            cwd=None,
            timeout=10.0,
            env=None,
        )
    if result is None:
        return ToolResult(name="checksec", args=args, stdout="", stderr="failed to run checksec", returncode=1, metadata={})

    return result


def ropgadget(*, binary: str | Path) -> ToolResult:
    bin_path = str(binary)
    argv = ["ROPgadget", "--binary", bin_path,"--only","pop|ret;"]
    result = _run_subprocess(
        name="ropgadget",
        argv=argv,
        args={"binary": bin_path, "argv": argv},
        cwd=None,
        timeout=10.0,
        env=None,
    )
    return result


def _filter_pwntools_output(text: str) -> str:
    import re
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    return text


def exp_runner(*, script_path: str | Path, cwd: str | Path | None = None, timeout: float = 15.0) -> ToolResult:
    script = Path(script_path).expanduser().resolve()
    run_cwd = Path(cwd).expanduser().resolve() if cwd is not None else script.parent
    argv = ["python3", str(script)]
    
    result = _run_subprocess(
        name="exp_runner",
        argv=argv,
        args={"script_path": str(script), "argv": argv, "cwd": str(run_cwd), "timeout": timeout},
        cwd=run_cwd,
        timeout=timeout,
        env=None,
    )

    _cleanup_gdb_processes()

    filtered_stdout = _filter_pwntools_output(result.stdout)
    filtered_stderr = _filter_pwntools_output(result.stderr)
    
    return ToolResult(
        name=result.name,
        args=result.args,
        stdout=filtered_stdout,
        stderr=filtered_stderr,
        returncode=result.returncode,
        metadata=result.metadata,
    )


class ToolRegistry:
    """内存中维护 tools: name -> function 的 KV 映射，并从 tools.json 加载 schema。"""

    def __init__(self) -> None:
        # 用于真正的函数执行
        self._tools: Dict[str, Callable[..., ToolResult]] = {
            "bash_execute": bash_execute,
            "grep_search": grep_search,
            "list_dir": list_dir,
            "file_read": file_read,
            "file_write": file_write,
            "exp_runner": exp_runner,
            "checksec": checksec,
            "ropgadget": ropgadget,
        }
        # 存储tools的name与description
        self._schemas_by_name: Dict[str, Dict[str, Any]] = {}
        if TOOLS_JSON.exists():
            try:
                data = json.loads(TOOLS_JSON.read_text(encoding="utf-8"))
                tools = list(data.get("tools", []))
                for schema in tools:
                    if not isinstance(schema, dict):
                        continue
                    fn = schema.get("function", {})
                    if not isinstance(fn, dict):
                        continue
                    name = str(fn.get("name", "")).strip()
                    if name:
                        self._schemas_by_name[name] = schema
            except Exception:
                self._schemas_by_name = {}

    @property
    def schemas(self) -> List[Dict[str, Any]]:
        """返回 tools.json 中定义的工具 schema，供 LLM function-calling 使用。"""

        return list(self._schemas_by_name.values())

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def run(self, name: str, **kwargs: Any) -> ToolResult:
        fn = self._tools.get(name)
        if fn is None:
            return ToolResult(
                name=name,
                args=dict(kwargs),
                stdout="",
                stderr=f"unknown tool: {name}",
                returncode=1,
                metadata={"error": "unknown-tool"},
            )
        try:
            return fn(**kwargs)
        except Exception as exc:
            return ToolResult(
                name=name,
                args=dict(kwargs),
                stdout="",
                stderr=f"tool failed: {exc}",
                returncode=1,
                metadata={"error": "tool-exception"},
            )

    def list_tools(self) -> str:
        """以 markdown 形式返回当前可用工具的简要清单，用于注入到 system/user prompt。

        仅使用 tools.json 中的 name/description 元信息。"""

        parts: List[str] = ["<tools>\n"]
        for schema in self.schemas:
            fn = schema.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            if not name:
                continue
            parts.append(f"\n## {name}\n\n{desc}\n")
        parts.append("\n</tools>\n")
        return "".join(parts)
