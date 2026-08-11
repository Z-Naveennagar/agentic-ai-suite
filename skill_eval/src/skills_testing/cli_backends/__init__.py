"""
Skill-test CLI backends.

These are *separate* from the existing top-level cli_backends/ package
(which is shaped around single-shot Q&A queries). The skill-test runner
needs a different contract: it spawns an agentic CLI inside a workspace
directory, lets it use tools, and consumes whatever artifacts it
produces on disk plus stdout/stderr.

Backends here implement skills_testing.cli_backends.interface.SkillBackend
(via base.SkillCLIBackend for the subprocess-driven ones) and are looked up
via get(client_name, model). ``get`` always returns something implementing
that interface -- NullSkillCLI when the client isn't wired up -- so callers
never need capability checks.
"""

from __future__ import annotations

from pathlib import Path

from .base import NullSkillCLI, SkillCLIBackend
from .interface import InvokeResult, SkillBackend, TokenUsage

__all__ = [
    "SkillBackend", "SkillCLIBackend", "NullSkillCLI",
    "InvokeResult", "TokenUsage",
    "get", "list_clients", "format_for", "skills_dir_for",
    "resolve_skills_root_for_client",
]


def _import_real() -> dict:
    out = {}
    try:
        from .claude_code import ClaudeCodeSkillCLI
        out["claude_code"] = ClaudeCodeSkillCLI
    except Exception:
        pass
    try:
        from .cursor import CursorSkillCLI
        out["cursor"] = CursorSkillCLI
    except Exception:
        pass
    try:
        from .copilot import CopilotSkillCLI
        out["copilot"] = CopilotSkillCLI
    except Exception:
        pass
    try:
        from .opencode import OpencodeSkillCLI
        out["opencode"] = OpencodeSkillCLI
    except Exception:
        pass
    return out


_REGISTRY: dict[str, type] = {}


def _ensure_registry() -> None:
    if _REGISTRY:
        return
    _REGISTRY.update(_import_real())


def get(client: str, model: str, config: dict | None = None) -> SkillBackend:
    """Return a SkillBackend for *client*/*model*.

    Falls back to NullSkillCLI (``is_available`` False) if the client isn't
    wired or its binary isn't installed -- the runner still records a row so
    the dashboard has data, but the case is SKIPPED rather than run.

    *config* is the full loaded config.yaml dict (optional). When given,
    ``cli_backends.<client>.bin_path`` is used to locate the binary ahead
    of the client's env var override / PATH search -- see
    SkillCLIBackend._find_binary().
    """
    _ensure_registry()
    cls = _REGISTRY.get(client)
    if cls is None:
        return NullSkillCLI(client, model, reason=f"unknown client {client!r}")
    bin_path = (((config or {}).get("cli_backends") or {}).get(client) or {}).get("bin_path")
    try:
        return cls(model, bin_path=bin_path)
    except Exception as exc:
        return NullSkillCLI(client, model, reason=str(exc))


def list_clients() -> list[str]:
    _ensure_registry()
    return sorted(_REGISTRY.keys())


def format_for(client: str) -> str:
    """Return the ``transcript_format`` a *client* emits, or ``""`` if unknown.

    Reads the attribute off the backend *class* without instantiating it, so
    this is safe to call at grade time on a host where the CLI binary (and thus
    a real backend instance) is unavailable. ``graders.trace`` uses the result
    to pick the matching tool-call parser instead of guessing.
    """
    _ensure_registry()
    cls = _REGISTRY.get(client)
    return getattr(cls, "transcript_format", "") or ""


def skills_dir_for(client: str) -> str:
    """Return the workspace-relative skill dir a *client* discovers.

    Reads ``workspace_skills_dir`` off the backend *class* without
    instantiating it (same rationale as ``format_for``): the workspace is
    staged before the CLI object exists, and constructing the CLI can fail
    when its binary is missing. Unknown clients fall back to the historical
    default ``.claude/skills``.
    """
    _ensure_registry()
    cls = _REGISTRY.get(client)
    return getattr(cls, "workspace_skills_dir", ".claude/skills") or ".claude/skills"


def resolve_skills_root_for_client(root: Path, client: str) -> Path:
    """Per-client skill SOURCE root actually staged into the workspace.

    ``root`` is the configured source (default the repo's ``.claude/skills``).
    opencode is instead linked to the sibling ``.opencode/skills`` source, so
    that its workspace folder, the symlink target, and any cache the skill
    writes back all stay under ``.opencode`` rather than crossing into
    ``.claude``. The destination folder name is already client-specific (see
    ``skills_dir_for``); this makes the source match it.

    Falls back to the configured root when the layout is custom (root not
    ending in ``.claude/skills``) or the sibling doesn't exist, so a client
    without its own installed source still gets the skills. This is the
    single source of truth for the mapping -- ``SkillRunner`` and any
    startup logging must call this rather than re-deriving it, so what gets
    printed always matches what gets staged.
    """
    tail = skills_dir_for(client)                     # e.g. ".opencode/skills"
    default_tail = SkillBackend.workspace_skills_dir  # ".claude/skills"
    if (
        tail != default_tail
        and root.name == "skills"
        and root.parent.name == ".claude"
    ):
        sibling = root.parent.parent / Path(tail)
        if sibling.is_dir():
            return sibling
    return root
