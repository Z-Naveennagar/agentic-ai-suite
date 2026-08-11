"""
Claude Code skill backend.

Spawns the bundled `claude` binary in non-interactive print mode against
the workspace directory. Skills, MCP config, and CLAUDE.md auto-discover
from the workspace + the user's home dir.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from .base import SkillCLIBackend
from .interface import TokenUsage


# Project-scoped MCP servers may not auto-resolve when claude is launched
# outside the project root, so we materialize an explicit --mcp-config
# pointing at the running Vivado MCP HTTP server. Override the default bridge
# URL with SKILL_TEST_VIVADO_MCP_URL when your MCP server runs elsewhere.
_DEFAULT_VIVADO_MCP_URL = "http://127.0.0.1:18090/mcp"
_DEFAULT_DOC_SEARCH_URL = "https://vivado.amd.com/mcp/doc-search"


# Map our short model name -> the full Claude Code model alias.
_MODEL_ALIAS = {
    "opus":     "opus",
    "sonnet":   "sonnet",
    "haiku":    "haiku",
}


def _find_claude_binary() -> Optional[str]:
    p = shutil.which("claude")
    if p and Path(p).resolve().exists():
        return p

    # Cursor IDE bundles claude under cursor-server extensions; pick the
    # newest installed version.
    ext_root = Path.home() / ".cursor-server" / "extensions"
    candidates: list[tuple[str, str]] = []
    if ext_root.is_dir():
        for sub in ext_root.iterdir():
            if not sub.name.startswith("anthropic.claude-code-"):
                continue
            bin_path = sub / "resources" / "native-binary" / "claude"
            if bin_path.is_file() and os.access(bin_path, os.X_OK):
                # Sort key: version string after "anthropic.claude-code-"
                ver = sub.name.removeprefix("anthropic.claude-code-")
                candidates.append((ver, str(bin_path)))
    if candidates:
        candidates.sort(key=lambda x: [
            int(p) if p.isdigit() else p for p in re.split(r"[.\-]", x[0])
        ])
        return candidates[-1][1]
    return None


class ClaudeCodeSkillCLI(SkillCLIBackend):
    name = "claude_code"
    binary_env_var = "CLAUDE_CODE_BIN"
    transcript_format = "anthropic_stream_json"  # --output-format stream-json

    def _default_binary_lookup(self) -> Optional[str]:
        return _find_claude_binary()

    def build_command(self, prompt: str, workspace_dir: Path) -> list[str]:
        # Project-scoped MCP servers don't follow us out of their project
        # dir, so materialize an explicit MCP config inside the workspace
        # that points at the running Vivado HTTP MCP server.
        mcp_cfg_path = workspace_dir / ".claude" / "mcp.json"
        mcp_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        if not mcp_cfg_path.exists():
            mcp_cfg_path.write_text(json.dumps({
                "mcpServers": {
                    "vivado-mcp-server": {
                        "type": "http",
                        "url": os.environ.get(
                            "SKILL_TEST_VIVADO_MCP_URL",
                            _DEFAULT_VIVADO_MCP_URL,
                        ),
                    },
                    "vivado-doc-search": {
                        "type": "http",
                        "url": os.environ.get(
                            "SKILL_TEST_DOC_SEARCH_URL",
                            _DEFAULT_DOC_SEARCH_URL,
                        ),
                    },
                }
            }, indent=2))

        cmd = [
            self.binary,
            "-p",                                      # non-interactive print
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",
            "--add-dir", str(workspace_dir),
            "--dangerously-skip-permissions",
            "--no-session-persistence",
            "--mcp-config", str(mcp_cfg_path),
        ]
        model_alias = _MODEL_ALIAS.get(self.model, self.model)
        if model_alias:
            cmd += ["--model", model_alias]
        cmd.append(prompt)
        return cmd

    def invoke(self, *, prompt: str, workspace_dir: Path,
               timeout_seconds: int, env: Optional[dict] = None) -> dict:
        result = super().invoke(
            prompt=prompt, workspace_dir=workspace_dir,
            timeout_seconds=timeout_seconds, env=env,
        )
        cost_usd = self._extract_native_cost_usd(result.get("stdout") or "")
        if cost_usd is not None:
            result["cost_usd"] = cost_usd
            result["cost_method"] = "native_cli_reported"
        return result

    @staticmethod
    def _extract_native_cost_usd(stdout: str) -> Optional[float]:
        """Claude Code prices its own usage: the terminal stream-json
        ``type:"result"`` line carries ``total_cost_usd``, already summed
        across every model used in the turn (including any Haiku
        sub-agent calls) -- no need to reprice it from ``pricing.yaml``
        when it's right there.
        """
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{") or '"total_cost_usd"' not in line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(obj, dict) and obj.get("type") == "result":
                cost = obj.get("total_cost_usd")
                if isinstance(cost, (int, float)):
                    return float(cost)
        return None

    def parse_token_usage(self, stdout: str, stderr: str) -> Optional[TokenUsage]:
        """Walk the Claude Code stream-json envelope and aggregate live
        plus cache token counts. Anthropic's wire schema is::

            "usage": {
                "input_tokens":                <live input>,
                "output_tokens":               <live output>,
                "cache_read_input_tokens":     <prompt-cache hits>,
                "cache_creation_input_tokens": <prompt-cache writes>
            }

        ``usage`` blocks are nested at varying depths across event types, so
        we walk each JSONL record rather than matching a fixed path. Input
        and cache counts on ``*message*``-typed records are running totals
        (Anthropic reissues them per chunk) and take ``max()``; output is
        per-delta and sums.
        """
        pin = pout = cread = cwrite = 0

        def _walk(node) -> None:
            nonlocal pin, pout, cread, cwrite
            if isinstance(node, dict):
                usage = node.get("usage")
                if isinstance(usage, dict):
                    running = "message" in (node.get("type") or "")
                    _i = usage.get("input_tokens") or 0
                    _o = usage.get("output_tokens") or 0
                    _cr = usage.get("cache_read_input_tokens") or 0
                    _cw = usage.get("cache_creation_input_tokens") or 0
                    if isinstance(_i, int):
                        pin = max(pin, _i) if running else pin + _i
                    if isinstance(_o, int):
                        pout += _o
                    if isinstance(_cr, int):
                        cread = max(cread, _cr) if running else cread + _cr
                    if isinstance(_cw, int):
                        cwrite = max(cwrite, _cw) if running else cwrite + _cw
                for value in node.values():
                    _walk(value)
            elif isinstance(node, list):
                for value in node:
                    _walk(value)

        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                _walk(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue

        return TokenUsage(input=int(pin), output=int(pout),
                          cache_read=int(cread), cache_write=int(cwrite))
