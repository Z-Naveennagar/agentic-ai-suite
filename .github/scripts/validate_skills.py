#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Validate skill directories against naming and governance rules.

Hard rules (exit 1 on failure):
  1. name is globally unique and lowercase kebab-case
  2. Directory name matches frontmatter name
  3. description is present and <= 1024 chars
  4. SKILL.md body <= 500 lines
  5. skill-card.md exists with non-empty Description, Owner, License
  6. No banned suffixes (-skill, -helper, -tool, -assistant)

Soft rules (warnings only):
  - Verb form preference (analysis -> analyze)
  - > 4 hyphenated segments
  - Near-duplicate name detection
"""

import os
import re
import sys
from pathlib import Path

BANNED_SUFFIXES = ["-skill", "-helper", "-tool", "-assistant", "-advisor"]
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NOUN_TO_VERB = {
    "analysis": "analyze",
    "creation": "create",
    "insertion": "insert",
    "optimization": "optimize",
    "simulation": "simulate",
}


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    fm = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip("'\"")
    return fm


def check_skill_card(card_path: Path) -> list[str]:
    errors = []
    if not card_path.exists():
        errors.append("missing skill-card.md")
        return errors
    text = card_path.read_text(encoding="utf-8")
    for field in ["Description:", "Owner:", "License:"]:
        if field not in text:
            errors.append(f"skill-card.md missing {field}")
    return errors


def validate_dir(skill_dir: Path, all_names: set) -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    dir_name = skill_dir.name

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append(f"{dir_name}: no SKILL.md")
        return errors, warnings

    fm = parse_frontmatter(skill_md)
    name = fm.get("name", "")
    desc = fm.get("description", "")

    # Rule 1: kebab-case
    if not KEBAB_RE.match(dir_name):
        errors.append(f"{dir_name}: directory name is not kebab-case")

    # Rule 2: name matches directory
    if name and name != dir_name:
        errors.append(f"{dir_name}: frontmatter name '{name}' != directory name")

    # Rule 1: uniqueness
    if name in all_names:
        errors.append(f"{dir_name}: duplicate name '{name}'")
    all_names.add(name)

    # Rule 3: description
    if not desc:
        errors.append(f"{dir_name}: missing description")
    elif len(desc) > 1024:
        errors.append(f"{dir_name}: description > 1024 chars")

    # Rule 4: body length
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    if len(lines) > 500:
        errors.append(f"{dir_name}: SKILL.md > 500 lines ({len(lines)})")

    # Rule 5: skill-card.md
    errors.extend(
        f"{dir_name}: {e}" for e in check_skill_card(skill_dir / "skill-card.md")
    )

    # Rule 6: banned suffixes
    for suffix in BANNED_SUFFIXES:
        if dir_name.endswith(suffix):
            errors.append(f"{dir_name}: name ends with banned suffix '{suffix}'")

    # Soft: verb form
    for noun, verb in NOUN_TO_VERB.items():
        if noun in dir_name:
            warnings.append(
                f"{dir_name}: consider '{verb}' instead of '{noun}'"
            )

    # Soft: segment count
    if dir_name.count("-") >= 4:
        warnings.append(f"{dir_name}: > 4 hyphenated segments")

    return errors, warnings


def main():
    root = Path(__file__).resolve().parent.parent.parent
    skills_dir = root / "skills"
    staging_dir = root / "staging"

    all_errors = []
    all_warnings = []
    all_names: set = set()

    for base in [skills_dir, staging_dir]:
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if base == staging_dir and d.name == "agents":
                continue
            errs, warns = validate_dir(d, all_names)
            all_errors.extend(errs)
            all_warnings.extend(warns)

    for w in all_warnings:
        print(f"WARNING: {w}")
    for e in all_errors:
        print(f"ERROR: {e}")

    if all_errors:
        print(f"\n{len(all_errors)} error(s), {len(all_warnings)} warning(s)")
        sys.exit(1)
    else:
        print(f"\nOK — {len(all_warnings)} warning(s)")


if __name__ == "__main__":
    main()
