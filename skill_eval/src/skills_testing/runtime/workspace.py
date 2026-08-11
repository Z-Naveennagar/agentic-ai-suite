"""
Per-test workspace management.

Each skill test runs in its own scratch directory under *workspace_root*.
Inputs from the case (`inputs/` and any *external_inputs*)
are copied in once; the runner sets `cwd` to this directory so any tool
(Vivado, Vitis, scripts) writes here and not in the repo.

Cleanup wipes the directory by default. With keep_on_failure=True and
failed=True the directory is retained for triage.
"""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..core.paths import default_workspace_root, expand_path_template


def probe_workspace_root(root: str | os.PathLike) -> dict:
    """Return free-space / mount info for *root*."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(root))
    is_tmpfs = False
    try:
        # /proc/mounts on Linux
        with open("/proc/mounts") as f:
            best_match = ""
            best_kind = ""
            r_str = str(root.resolve()) + "/"
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mp = parts[1]
                if (r_str).startswith(mp.rstrip("/") + "/") or str(root.resolve()) == mp:
                    if len(mp) > len(best_match):
                        best_match = mp
                        best_kind = parts[2]
            is_tmpfs = best_kind == "tmpfs"
    except OSError:
        pass
    return {
        "root": str(root),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "is_tmpfs": is_tmpfs,
    }


@dataclass
class Workspace:
    case_id: str
    dir: Path
    inputs_dir: Path | None = None
    external_inputs: list[Any] = field(default_factory=list)
    skills_root: Path | None = None
    # Optional allowlist (list of "<top>" or "<top>/<sub>" paths
    # relative to skills_root). If set, the workspace stages only the
    # listed entries plus the top-level SKILL.md of each parent skill,
    # rather than symlinking the entire skills_root tree. Cuts the
    # token footprint when a test exercises a single sub-skill.
    skills_allowlist: list[str] = field(default_factory=list)
    # Workspace-relative directory into which ``skills_root`` is staged and
    # where the target CLI discovers skills. Claude Code / Copilot use
    # ``.claude/skills``; opencode uses ``.opencode/skills``. Defaults to
    # ``.claude/skills`` so callers that don't set it keep the historical
    # behaviour. The runner sets this per client via
    # ``cli_backends.skills_dir_for(client)``.
    skills_dest: str = ".claude/skills"
    # When False, ``populate()`` drops any external_inputs whose ``dest``
    # lands inside a skill root (``.claude/skills``/``.opencode/skills``/
    # ``.cursor``) so the no-skill arm cannot accidentally still see
    # SKILL.md trees that the manifest pulls in via external_inputs.
    # Default True preserves backwards compat for callers that don't go
    # through ``SkillRunner._run_one``.
    allow_skill_inputs: bool = True
    _populated: bool = False

    def populate(self) -> None:
        """Copy inputs_dir/* and external_inputs into self.dir.

        If ``skills_root`` is set, materialise ``<workspace>/<skills_dest>``
        (``.claude/skills`` by default, ``.opencode/skills`` for opencode).
        With no ``skills_allowlist`` we symlink the whole tree (cheap,
        keeps full auto-discovery). With an allowlist we copy just the
        requested sub-skill bodies + each parent's top-level SKILL.md so
        the agent only sees the skills the test actually needs.
        """
        if self.inputs_dir is not None:
            src = Path(self.inputs_dir)
            if src.is_dir():
                for entry in src.iterdir():
                    dest = self.dir / entry.name
                    if entry.is_dir():
                        shutil.copytree(entry, dest)
                    else:
                        shutil.copy2(entry, dest)

        if self.skills_root is not None:
            sk_src = Path(self.skills_root).resolve()
            if not sk_src.exists():
                raise FileNotFoundError(
                    f"skills_root not found: {sk_src}"
                )
            link_dest = self.dir / self.skills_dest
            link_dest.parent.mkdir(parents=True, exist_ok=True)
            if link_dest.exists() or link_dest.is_symlink():
                if link_dest.is_symlink() or link_dest.is_dir():
                    try:
                        link_dest.unlink()
                    except IsADirectoryError:
                        shutil.rmtree(link_dest, ignore_errors=True)

            if not self.skills_allowlist:
                os.symlink(sk_src, link_dest, target_is_directory=True)
            else:
                _stage_skills_subset(
                    sk_src, link_dest, self.skills_allowlist,
                )

        skipped_skill_inputs: list[str] = []
        for ext in self.external_inputs:
            if isinstance(ext, dict):
                src = expand_path_template(ext["src"])
                dest_rel = ext.get("dest") or src.name
            else:
                src = expand_path_template(ext)
                dest_rel = src.name
            # NO-SKILL arm: any external input that lands inside
            # .claude/skills/ leaks SKILL.md material into the workspace,
            # which CWD-walking CLIs (claude_code, opencode, copilot)
            # then auto-discover regardless of any env-var hiding. Drop
            # those entries; the SKILL arm gets the same skills via
            # ``skills_root`` (or its own external_inputs list when
            # allow_skill_inputs=True). Captured so the runner can log it.
            dest_norm = str(dest_rel).replace("\\", "/")
            while dest_norm.startswith("./"):
                dest_norm = dest_norm[2:]
            if not self.allow_skill_inputs and _is_skill_dest(dest_norm):
                skipped_skill_inputs.append(dest_norm)
                continue
            if not src.exists():
                raise FileNotFoundError(f"external input not found: {src}")
            dest = self.dir / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)
        # Surface skipped paths for runner-side logging without forcing
        # a callback dependency.
        self._skipped_skill_inputs = skipped_skill_inputs
        self._populated = True

    def cleanup(self, *, keep_on_failure: bool = False, failed: bool = False) -> None:
        if keep_on_failure and failed:
            return
        if self.dir.exists():
            shutil.rmtree(self.dir, ignore_errors=True)

    def size_bytes(self) -> int:
        total = 0
        for root, _, files in os.walk(self.dir):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
        return total


_SKILL_DEST_PREFIXES = (
    ".claude/skills/", ".claude/skills",
    "claude/skills/", "claude/skills",
    ".opencode/skills/", ".opencode/skills",
    "opencode/skills/", "opencode/skills",
    ".cursor/skills/", ".cursor/skills",
    ".cursor/rules/", ".cursor/rules",
)


def _is_skill_dest(dest_norm: str) -> bool:
    """Return True if *dest_norm* would land skill material in the workspace."""
    for prefix in _SKILL_DEST_PREFIXES:
        if dest_norm == prefix or dest_norm.startswith(prefix + "/"):
            return True
        if prefix.endswith("/") and dest_norm.startswith(prefix):
            return True
    if dest_norm == "AGENTS.md" or dest_norm.endswith("/AGENTS.md"):
        return True
    return False


def create_workspace(
    case_id: str,
    *,
    root: str | os.PathLike | None = None,
    inputs_dir: str | os.PathLike | None = None,
    external_inputs: Iterable[Any] | None = None,
    skills_root: str | os.PathLike | None = None,
    skills_allowlist: Iterable[str] | None = None,
    skills_dest: str = ".claude/skills",
    allow_skill_inputs: bool = True,
) -> Workspace:
    root = Path(root).expanduser() if root is not None else default_workspace_root()
    root.mkdir(parents=True, exist_ok=True)
    safe_id = case_id.replace("/", "_").replace(" ", "_")
    name = f"skilltest-{safe_id}-{uuid.uuid4().hex[:8]}"
    ws_dir = root / name
    ws_dir.mkdir()
    return Workspace(
        case_id=case_id,
        dir=ws_dir,
        inputs_dir=Path(inputs_dir) if inputs_dir else None,
        external_inputs=list(external_inputs or []),
        skills_root=Path(skills_root) if skills_root else None,
        skills_allowlist=list(skills_allowlist or []),
        skills_dest=skills_dest,
        allow_skill_inputs=allow_skill_inputs,
    )


def _stage_skills_subset(
    src_root: Path, dest_root: Path, allowlist: list[str],
) -> None:
    """Materialise *dest_root* with only the entries in *allowlist*,
    plus the top-level ``SKILL.md`` of each parent skill.

    Each allowlist entry is a path relative to *src_root*:
      * ``"rtl-assistant"`` stages the whole top-level skill
      * ``"rtl-assistant/report_methodology"`` stages just that sub-skill,
        plus ``rtl-assistant/SKILL.md`` so the parent descriptor is still
        discoverable.

    Uses symlinks to avoid re-copying the bytes; callers that need an
    isolated copy can ``shutil.copytree`` the result.
    """
    dest_root.mkdir(parents=True, exist_ok=True)
    needed_parent_descriptors: set[str] = set()
    for entry in allowlist:
        parts = entry.strip("/").split("/")
        if not parts or not parts[0]:
            continue
        src = src_root.joinpath(*parts)
        if not src.exists():
            raise FileNotFoundError(
                f"skill allowlist entry not found: {src}"
            )
        dest = dest_root.joinpath(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            try:
                dest.unlink()
            except IsADirectoryError:
                shutil.rmtree(dest, ignore_errors=True)
        os.symlink(src.resolve(), dest,
                   target_is_directory=src.is_dir())
        # If a sub-skill was requested, also stage the parent
        # SKILL.md so the agent finds the skill descriptor.
        if len(parts) > 1:
            needed_parent_descriptors.add(parts[0])

    for top in needed_parent_descriptors:
        parent_skill = dest_root / top / "SKILL.md"
        src_skill = src_root / top / "SKILL.md"
        if parent_skill.exists() or parent_skill.is_symlink():
            continue
        if src_skill.exists():
            parent_skill.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(src_skill.resolve(), parent_skill)
