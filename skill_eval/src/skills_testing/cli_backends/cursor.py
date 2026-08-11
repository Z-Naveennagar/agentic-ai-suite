"""
Cursor ``agent`` skill backend.

The Cursor CLI is called ``agent`` (https://cursor.com/cli).
Spawns ``agent -p`` in the workspace dir.  Cursor auto-discovers
.cursor/ and .claude/skills/ from the workspace + user home.

A/B integrity: in the no-skill arm we override HOME to a clean temp
directory so the user's ~/.claude/skills/ cannot leak into the run.
The real HOME is preserved for binary lookup and API key resolution
(CURSOR_API_KEY lives in ~/.bashrc which is not sourced by subprocess).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from .base import SkillCLIBackend
from .interface import TokenUsage


# Cursor auto-discovers a project-scoped MCP config at ``.cursor/mcp.json``
# in the workspace. When ``agent`` is launched with ``--workspace`` outside
# the project root the parent repo's MCP servers don't follow, so we
# materialize an explicit config pointing at the running Vivado HTTP MCP
# server (mirrors the claude_code / copilot / opencode backends). Override
# the bridge URL with SKILL_TEST_VIVADO_MCP_URL when it runs elsewhere.
_DEFAULT_VIVADO_MCP_URL = "http://127.0.0.1:18090/mcp"
_DEFAULT_DOC_SEARCH_URL = "https://vivado.amd.com/mcp/doc-search"


class CursorSkillCLI(SkillCLIBackend):
    name = "cursor"
    binary_env_var = "AGENT_BIN"
    transcript_format = "cursor_json"  # --output-format stream-json (JSONL)

    def _default_binary_lookup(self) -> Optional[str]:
        # The Cursor CLI binary is ``agent``
        # (https://cursor.com/cli, ``agent --help``).
        # Installed by ``curl https://cursor.com/install | bash``
        # into ~/.local/bin/agent.
        p = shutil.which("agent")
        if p:
            return p
        local = Path.home() / ".local" / "bin" / "agent"
        if local.exists():
            return str(local)
        return None

    def build_command(self, prompt: str, workspace_dir: Path) -> list[str]:
        self._write_mcp_config(workspace_dir)
        cmd = [
            self.binary,
            "-p",
            # stream-json (JSONL) so per-turn tool_call events are captured for
            # the action_sequence grader. The older `json` format emitted only
            # a single terminal `type:result` doc with no tool events.
            "--output-format", "stream-json",
            "--force",
            "--approve-mcps",
            "--trust",
            "--workspace", str(workspace_dir),
        ]
        if self.model:
            cmd += ["--model", self.model]
        cmd.append(prompt)
        return cmd

    def _write_mcp_config(self, workspace_dir: Path) -> None:
        """Materialize the workspace-local ``.cursor/mcp.json`` Cursor
        auto-discovers, wiring the Vivado MCP + doc-search HTTP servers.

        Written in both A/B arms (only skills differ between arms; MCP
        access is needed either way). Cursor picks the transport from the
        ``url`` scheme, so remote servers need only a ``url`` entry.
        """
        cfg_path = workspace_dir / ".cursor" / "mcp.json"
        if cfg_path.exists():
            return
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps({
            "mcpServers": {
                "vivado-mcp-server": {
                    "url": os.environ.get(
                        "SKILL_TEST_VIVADO_MCP_URL", _DEFAULT_VIVADO_MCP_URL,
                    ),
                },
                "vivado-doc-search": {
                    "url": os.environ.get(
                        "SKILL_TEST_DOC_SEARCH_URL", _DEFAULT_DOC_SEARCH_URL,
                    ),
                },
            }
        }, indent=2))

    def invoke(self, *, prompt: str, workspace_dir: Path,
               timeout_seconds: int, env: Optional[dict] = None) -> dict:
        overrides: dict[str, str] = {}
        if env:
            overrides.update(env)

        # A/B integrity: when skill_hider sets CURSOR_SKILLS_DIR=/dev/null
        # that signals the no-skill arm. Redirect HOME to an empty temp dir
        # so ~/.claude/skills/ and ~/.cursor/rules/ are invisible. We keep
        # the API key and PATH from the real environment.
        fake_home = None
        if overrides.get("CURSOR_SKILLS_DIR") == "/dev/null":
            fake_home = tempfile.mkdtemp(prefix="cursor_noskill_home_")
            overrides["HOME"] = fake_home
            real_home = os.environ.get("HOME", "")
            for key in ("CURSOR_API_KEY", "COPILOT_GITHUB_TOKEN",
                        "XILINXD_LICENSE_FILE", "NODE_OPTIONS",
                        "NODE_EXTRA_CA_CERTS"):
                if key not in overrides and key in os.environ:
                    overrides[key] = os.environ[key]

        try:
            return super().invoke(
                prompt=prompt, workspace_dir=workspace_dir,
                timeout_seconds=timeout_seconds, env=overrides,
            )
        finally:
            if fake_home:
                shutil.rmtree(fake_home, ignore_errors=True)

    @staticmethod
    def _final_result_obj(stdout: str) -> dict:
        """The terminal ``type:result`` envelope from Cursor's stream-json.

        stream-json stdout is JSONL: one JSON object per line, ending with a
        ``{"type":"result", ..., "usage":{...}}`` line. We scan for the last
        object carrying a ``usage`` block (falling back to any ``type:result``).
        A single-object ``--output-format json`` payload parses as one line, so
        this also handles the legacy format.
        """
        found: dict = {}
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("usage") or obj.get("type") == "result":
                found = obj
        return found

    def parse_token_usage(self, stdout: str, stderr: str) -> Optional[TokenUsage]:
        """Cursor's stream-json terminal ``result`` envelope reports four
        token counts in camelCase under ``usage``::

            "usage": {
                "inputTokens":      <live input tokens this turn>,
                "outputTokens":     <live output tokens this turn>,
                "cacheReadTokens":  <prompt-cache hits>,
                "cacheWriteTokens": <prompt-cache writes>
            }

        We surface all four so the cost model can price the cache
        traffic at Anthropic's cache rates instead of dropping it. The
        snake_case aliases cover older Cursor builds.
        """
        usage = (self._final_result_obj(stdout) or {}).get("usage") or {}
        if not usage:
            return None

        def _pick(*keys: str) -> int:
            for key in keys:
                value = usage.get(key)
                if value:
                    return int(value)
            return 0

        return TokenUsage(
            input=_pick("inputTokens", "input_tokens", "prompt_tokens"),
            output=_pick("outputTokens", "output_tokens", "completion_tokens"),
            cache_read=_pick("cacheReadTokens", "cache_read_tokens",
                             "cache_read_input_tokens"),
            cache_write=_pick("cacheWriteTokens", "cache_write_tokens",
                              "cache_creation_input_tokens"),
        )
