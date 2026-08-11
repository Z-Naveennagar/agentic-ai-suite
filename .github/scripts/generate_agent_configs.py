#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Generate agent configuration files from skill frontmatter.

Reads skills/*/SKILL.md frontmatter to produce:
  - CLAUDE.md (skill index)
  - AGENTS.md (Codex format)
  - .github/copilot-instructions.md
  - .cursor/rules/skills.mdc
  - .claude-plugin/marketplace.json

Only the skill index portion is generated. Agent-specific preambles are
hand-written in templates/ if needed.
"""

import json
from pathlib import Path

import yaml


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    fm_text = text[3:end].strip()
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return {k: str(v).strip() for k, v in fm.items() if v is not None}


def load_skills(skills_dir: Path) -> list[dict]:
    skills = []
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        skill_md = d / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = parse_frontmatter(skill_md)
        if fm.get("name") and fm.get("description"):
            triggers = fm.get("triggers", "")
            skills.append({
                "name": fm["name"],
                "description": fm["description"][:200],
                "path": f"skills/{d.name}/SKILL.md",
                "triggers": triggers,
            })
    return skills


def generate_claude_md(skills: list[dict], root: Path):
    lines = [
        "# Agentic AI Suite",
        "",
        "Unified repository for AMD FPGA/SoC agent skills. "
        "Skills are organized flat under `skills/`.",
        "",
        "## How to Use",
        "",
        "When a user's request matches one of the skill descriptions below, "
        "read the corresponding SKILL.md file and follow its instructions.",
        "",
        "## Skills",
        "",
    ]

    for s in skills:
        lines.append(f'- **{s["name"]}** — `{s["path"]}`')
        lines.append(f"  {s['description'][:120]}")
        if s.get("triggers"):
            lines.append(f'  Triggers: {s["triggers"]}')
    lines.append("")

    (root / "CLAUDE.md").write_text("\n".join(lines), encoding="utf-8")


def generate_agents_md(skills: list[dict], root: Path):
    lines = [
        "# Agent Skills",
        "",
        "This file lists available skills for AI coding agents.",
        "",
    ]

    for s in skills:
        lines.append(f"## {s['name']}")
        lines.append(f"- Path: `{s['path']}`")
        lines.append(f"- Description: {s['description'][:200]}")
        lines.append("")

    (root / "AGENTS.md").write_text("\n".join(lines), encoding="utf-8")


def generate_copilot_instructions(skills: list[dict], root: Path):
    lines = [
        "# AMD FPGA/SoC Agent Skills",
        "",
        "When a user request matches a skill description, read the SKILL.md "
        "at the listed path and follow its instructions.",
        "",
    ]

    for s in skills:
        lines.append(f"- **{s['name']}**: {s['description'][:120]} "
                     f"→ `{s['path']}`")
    lines.append("")

    out = root / ".github" / "copilot-instructions.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def generate_cursor_rules(skills: list[dict], root: Path):
    lines = [
        "---",
        "description: AMD FPGA/SoC skill routing",
        "globs: **/*",
        "---",
        "",
        "# AMD Agentic AI Suite — Skill Index",
        "",
        "When a user request matches a skill, read the SKILL.md at the "
        "listed path.",
        "",
    ]

    for s in skills:
        lines.append(f"- {s['name']}: `{s['path']}`")
    lines.append("")

    out = root / ".cursor" / "rules" / "skills.mdc"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def generate_marketplace(skills: list[dict], root: Path):
    plugin_meta_path = root / "plugin-metadata.json"
    meta = {}
    if plugin_meta_path.exists():
        meta = json.loads(plugin_meta_path.read_text(encoding="utf-8"))

    manifest = {
        "name": meta.get("name", "xilinx-agentic-ai-suite"),
        "display_name": meta.get("display_name", "AMD/Xilinx Agentic AI Suite"),
        "description": meta.get("description", ""),
        "version": meta.get("version", "0.7.0"),
        "skills": [
            {
                "name": s["name"],
                "description": s["description"][:200],
                "path": s["path"],
            }
            for s in skills
        ],
    }

    out = root / ".claude-plugin" / "marketplace.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    root = Path(__file__).resolve().parent.parent.parent
    skills_dir = root / "skills"

    skills = load_skills(skills_dir)

    generate_claude_md(skills, root)
    generate_agents_md(skills, root)
    generate_copilot_instructions(skills, root)
    generate_cursor_rules(skills, root)
    generate_marketplace(skills, root)

    print(f"Generated configs for {len(skills)} skills")


if __name__ == "__main__":
    main()
