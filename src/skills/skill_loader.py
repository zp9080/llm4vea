from __future__ import annotations

from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = PROJECT_ROOT / "inputs" / "skills"


def read_markdown_files(files: Iterable[Path]) -> str:
    parts: list[str] = []
    for path in files:
        if not path.exists():
            continue
        parts.append(f"\n\n# {path.stem}\n\n")
        parts.append(path.read_text(encoding="utf-8"))
    return "".join(parts)

def _extract_skill_header(path: Path) -> str:
    """从 SKILL.md 中抽取头部（name/description 部分）。"""

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header_lines: list[str] = []
    in_frontmatter = False

    # 抽取 YAML frontmatter（--- name/description ---）
    for line in lines:
        stripped = line.strip()
        if not in_frontmatter:
            if stripped == "---":
                in_frontmatter = True
                header_lines.append(line)
        else:
            header_lines.append(line)
            if stripped == "---":
                break

    return "\n".join(header_lines)

# 只用于内部固定的skill加载，如果是agent自行加载skill，那么直接使用file_read工具即可
def load_skill(type: str, name: str) -> str:
    base = SKILLS_ROOT / type
    if not base.exists():
        return ""
    if name == "SKILL":
        path = base / "SKILL.md"
    else:
        filename = name if name.endswith(".md") else f"{name}.md"
        path = base / filename
    return read_markdown_files([path])

# 列举出所有的SKILL.md
def list_skills() -> str:
    """返回一个紧凑的 skills 索引，仅包含各 SKILL.md 的头部信息。
    """

    parts: list[str] = ["<skills>\n"]

    core_skill = SKILLS_ROOT / "core" / "SKILL.md"
    if core_skill.exists():
        parts.append("\n<core skill>\n")
        parts.append(_extract_skill_header(core_skill))
        parts.append("\n</core skill>\n")

    vuln_root = SKILLS_ROOT / "vuln"
    vuln_root_skill = vuln_root / "SKILL.md"
    if vuln_root_skill.exists():
        parts.append("\n<vuln skill>\n")
        parts.append(_extract_skill_header(vuln_root_skill))
        parts.append("\n")

        for sub in sorted(vuln_root.iterdir()):
            if not sub.is_dir():
                continue
            skill_file = sub / "SKILL.md"
            if not skill_file.exists():
                continue
            parts.append(f"\n<{sub.name} skill>\n")
            parts.append(_extract_skill_header(skill_file))
            parts.append(f"\n</{sub.name} skill>\n")

        parts.append("\n</vuln skill>\n")

    edge_skill = SKILLS_ROOT / "edge" / "SKILL.md"
    if edge_skill.exists():
        parts.append("\n<edge skill>\n")
        parts.append(_extract_skill_header(edge_skill))
        parts.append("\n</edge skill>\n")

    parts.append("\n</skills>\n")
    return "".join(parts)
