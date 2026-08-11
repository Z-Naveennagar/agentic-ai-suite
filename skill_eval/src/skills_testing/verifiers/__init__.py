"""Verifier callables consumed by SkillRunner's verify_by_rerun (Phase 2b)
hook. Each verifier signature matches:

    verifier(*, workspace_dir: Path, tcl: str,
             env: dict | None, timeout_seconds: int) -> dict

returning ``{"stdout": str, "stderr": str, "exit_code": int}``.
"""
from __future__ import annotations

from .vivado_mcp import vivado_mcp_verifier  # noqa: F401
