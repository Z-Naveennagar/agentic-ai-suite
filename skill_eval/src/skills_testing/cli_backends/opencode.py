"""OpenCode backend for skill-test runs.

This backend is intentionally workspace-aware: it writes a project-local
`opencode.json` so OpenCode sees the staged skill tree and the configured
Vivado MCP endpoint from inside the isolated test workspace.

To prevent OpenCode from auto-discovering the parent repo (which creates
multiple project instances and causes path mismatches — the agent writes
files relative to the repo root, but the grader reads from the workspace),
we pin OpenCode to the workspace with ``--dir`` and force config resolution
via ``OPENCODE_CONFIG``. This mirrors claude code's ``--add-dir`` pattern.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import urllib.request
from pathlib import Path
from typing import Optional

from .base import SkillCLIBackend
from .interface import TokenUsage


_DEFAULT_VIVADO_MCP_URL = "http://127.0.0.1:18090/mcp"
_DEFAULT_DOC_SEARCH_URL = "https://vivado.amd.com/mcp/doc-search"
_DEFAULT_LEMONADE_URL = "http://127.0.0.1:8000/api/v1"
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lemonade_dispatch_lock(base_url: str) -> threading.Lock:
    """Return a per-Lemonade-endpoint lock to avoid concurrent local overload."""
    with _LOCKS_GUARD:
        if base_url not in _LOCKS:
            _LOCKS[base_url] = threading.Lock()
        return _LOCKS[base_url]


class OpencodeSkillCLI(SkillCLIBackend):
    name = "opencode"
    binary_env_var = "OPENCODE_BIN"
    transcript_format = "opencode_logs"  # --print-logs (arrow + gear glyphs)
    # opencode discovers project skills under ``.opencode/skills`` (and, when
    # declared, whatever ``skills.paths`` in opencode.json points at). The
    # runner stages the skill tree here instead of ``.claude/skills`` so the
    # workspace copy is what this client sees.
    workspace_skills_dir = ".opencode/skills"

    def _default_binary_lookup(self) -> Optional[str]:
        home_bin = Path.home() / ".opencode" / "bin" / "opencode"
        if home_bin.is_file() and os.access(home_bin, os.X_OK):
            return str(home_bin)
        return shutil.which("opencode")

    def build_command(self, prompt: str, workspace_dir: Path) -> list[str]:
        self._write_opencode_config(workspace_dir)
        return [
            self.binary, "run", prompt,
            "--print-logs",
            "--dir", str(workspace_dir),
            "--model", self.model,
        ]

    def invoke(
        self, *, prompt: str, workspace_dir: Path,
        timeout_seconds: int, env: Optional[dict] = None,
    ) -> dict:
        # OpenCode keeps a single shared SQLite store at
        # ``$XDG_DATA_HOME/opencode/opencode.db``. When several
        # ``opencode run`` processes start concurrently (the scheduler runs
        # tests in parallel, and every rep0 launches at once) they contend
        # on that one DB; the 5s busy_timeout is not enough during startup
        # migrations, so a loser dies with "database is locked", emits no
        # output, and the run is mis-scored as "skill not invoked".
        #
        # OpenCode honours ``OPENCODE_DB``: an absolute path overrides the
        # store location. Each test already gets its own isolated
        # workspace, so we pin the DB inside it -> per-process database, no
        # cross-process lock. Auth lives under ``$XDG_CONFIG_HOME/opencode``
        # (not in opencode.db), so credentials are unaffected.
        #
        # OpenCode also walks up from cwd looking for git repos and
        # opencode.json files, which can cause it to discover the parent
        # repo and create additional project instances. Setting
        # ``OPENCODE_CONFIG`` to the workspace-local opencode.json forces
        # config resolution to stay within the isolated workspace.
        merged = dict(env or {})
        if "OPENCODE_DB" not in merged:
            db_dir = Path(workspace_dir) / ".opencode"
            db_dir.mkdir(parents=True, exist_ok=True)
            merged["OPENCODE_DB"] = str(db_dir / "opencode.db")
        if "OPENCODE_CONFIG" not in merged:
            merged["OPENCODE_CONFIG"] = str(Path(workspace_dir) / "opencode.json")
        result = super().invoke(
            prompt=prompt, workspace_dir=workspace_dir,
            timeout_seconds=timeout_seconds, env=merged,
        )
        session = self._read_session_row(merged["OPENCODE_DB"])
        if session is not None:
            usage, cost_usd = session
            result["prompt_tokens"] = usage.input
            result["output_tokens"] = usage.output
            result["total_tokens"] = usage.total
            result["cache_read_tokens"] = usage.cache_read
            result["cache_write_tokens"] = usage.cache_write
            if cost_usd is not None:
                result["cost_usd"] = cost_usd
                result["cost_method"] = "native_cli_reported"
        return result

    @staticmethod
    def _read_session_row(db_path: str) -> Optional[tuple[TokenUsage, Optional[float]]]:
        """Real per-session token counts AND cost, straight from opencode's
        own store.

        opencode computes and persists real usage and its own cost estimate
        per session in the ``session`` table -- no ``--json`` flag exists on
        ``opencode run``/``stats`` to get this from stdout, so we read the
        sqlite file directly instead of re-parsing text. ``OPENCODE_DB`` is
        pinned to a workspace-local file (see ``invoke`` above), and
        shared-fixture groups reuse one workspace across several cases, so a
        file can carry more than one session -- take the most recently
        updated row, which is always the one this ``invoke()`` call just
        created.

        Reasoning tokens (present for reasoning models) are folded into
        ``output`` since they're billed at the output rate everywhere in
        ``pricing.yaml``; opencode has no separate reasoning-token price.
        Never fatal: a DB we can't read costs real usage, not the run.
        """
        try:
            uri = f"file:{db_path}?mode=ro"
            con = sqlite3.connect(uri, uri=True, timeout=5)
            try:
                row = con.execute(
                    "SELECT tokens_input, tokens_output, tokens_reasoning, "
                    "tokens_cache_read, tokens_cache_write, cost FROM session "
                    "ORDER BY time_updated DESC LIMIT 1"
                ).fetchone()
            finally:
                con.close()
        except sqlite3.Error:
            return None
        if not row:
            return None
        tin, tout, treason, tcread, tcwrite, cost = row
        usage = TokenUsage(
            input=int(tin or 0),
            output=int(tout or 0) + int(treason or 0),
            cache_read=int(tcread or 0),
            cache_write=int(tcwrite or 0),
        )
        return usage, (float(cost) if cost is not None else None)

    def _write_opencode_config(self, workspace_dir: Path) -> None:
        cfg_path = workspace_dir / "opencode.json"
        if cfg_path.exists():
            return
        cfg_path.write_text(json.dumps({
            # Non-interactive ``opencode run`` auto-REJECTS every permission
            # left at OpenCode's default "ask", and a rejection raises
            # PermissionRejectedError, which tears the whole session down
            # mid-task instead of just blocking the one tool call. Seen in
            # run f2587ea2 rep1: a Glob for the skill's lib/ipcfg.tcl
            # resolved to $HOME (= /home here, and the workspace lives under
            # /home/.cache), tripped external_directory, and killed the run
            # 25s into an 1800s budget with no result to grade.
            #
            # "deny" is the *recoverable* form of the same restriction: the
            # tool call returns an ordinary error the model reads and works
            # around, and the agent loop continues (verified against
            # opencode 1.17.20).
            #
            # Deliberately NOT the `--auto`/`--yolo`/
            # `--dangerously-skip-permissions` flag, which is the obvious
            # fix and the wrong one: it ALLOWS reads under $HOME, and the
            # suites' golden answers live there (tests/*/*/
            # test_cases.yaml). That would let a blind benchmark read its
            # own answer key.
            "permission": {"external_directory": {"*": "deny"}},
            "mcp": {
                "vivado-mcp-server": {
                    "type": "remote",
                    "url": os.environ.get(
                        "SKILL_TEST_VIVADO_MCP_URL", _DEFAULT_VIVADO_MCP_URL,
                    ),
                    "enabled": True,
                },
                "vivado-doc-search": {
                    "type": "remote",
                    "url": os.environ.get(
                        "SKILL_TEST_DOC_SEARCH_URL", _DEFAULT_DOC_SEARCH_URL,
                    ),
                    "enabled": True,
                },
            }
        }, indent=2))

    def hide_skills_env_overrides(self) -> Optional[dict]:
        # OpenCode discovers project-local skills by walking the workspace.
        # The no-skill arm prevents leakage by not staging .claude/skills.
        return {}

    def preflight_skip(
        self, *, prompt: str, workspace_dir: Path, timeout_seconds: int,
    ) -> Optional[str]:
        if os.environ.get("SKILL_TEST_DISABLE_PREFLIGHT"):
            return None
        if not os.environ.get("SKILL_TEST_ENABLE_PREFLIGHT"):
            return None
        if not _is_lemonade_model(self.model):
            return None

        estimated_tokens = _estimate_prompt_tokens(prompt, workspace_dir)
        if estimated_tokens < int(os.environ.get("SKILL_TEST_PREFLIGHT_MIN_TOKENS", "1000")):
            return None

        try:
            tok_per_s = float(self._probe_prompt_per_second())
        except Exception:
            return None
        if tok_per_s <= 0:
            return None

        usable_budget = tok_per_s * max(1, timeout_seconds) * 0.70
        if estimated_tokens > usable_budget:
            return (
                "model_too_slow_for_prompt: "
                f"estimated_prompt_tokens={estimated_tokens} "
                f"budget_tokens={int(usable_budget)} "
                f"rate={tok_per_s:.1f} tok/s"
            )
        return None

    def _probe_prompt_per_second(self) -> float:
        """Probe a Lemonade-compatible endpoint for prompt-eval throughput.

        The exact response schema can vary, so this accepts a few common
        token-per-second field names and otherwise raises.
        """
        base = os.environ.get("LEMONADE_BASE_URL", _DEFAULT_LEMONADE_URL).rstrip("/")
        lock = _lemonade_dispatch_lock(base)
        with lock:
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=json.dumps({
                    "model": self.model.removeprefix("lemonade/"),
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {os.environ.get('LEMONADE_API_KEY', 'lemonade')}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        for key in ("prompt_tokens_per_second", "prompt_eval_rate", "tokens_per_second"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            for key in ("prompt_tokens_per_second", "prompt_eval_rate", "tokens_per_second"):
                value = usage.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        raise RuntimeError("Lemonade response did not include prompt throughput")


def _is_lemonade_model(model: str) -> bool:
    return model.lower().startswith("lemonade/")


def _estimate_prompt_tokens(prompt: str, workspace_dir: Path) -> int:
    chars = len(prompt or "")
    # opencode stages its skill tree under ``.opencode/skills``; earlier
    # workspaces used ``.claude/skills``. Sum whichever is present so the
    # throughput preflight keeps counting staged skill bytes after the
    # per-client folder split (and for any mixed/legacy workspace).
    for rel in (OpencodeSkillCLI.workspace_skills_dir, ".claude/skills"):
        skill_root = workspace_dir / rel
        if not skill_root.exists():
            continue
        for path in skill_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".txt", ".yaml", ".yml", ".json"}:
                continue
            try:
                chars += path.stat().st_size
            except OSError:
                continue
    return max(0, int(chars / 3.5))


__all__ = ["OpencodeSkillCLI", "_lemonade_dispatch_lock"]
