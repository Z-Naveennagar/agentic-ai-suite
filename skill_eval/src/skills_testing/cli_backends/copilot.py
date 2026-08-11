"""
GitHub Copilot CLI skill backend.

Spawns `copilot -p` non-interactively in the workspace directory. We
strip any user-level BYOK env vars so the test runs against
GitHub-hosted models, and we install a workspace-scoped
.copilot/mcp-config.json that points at the local Vivado MCP HTTP
server.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from .base import SkillCLIBackend
from .interface import TokenUsage


_DEFAULT_VIVADO_MCP_URL = "http://127.0.0.1:18090/mcp"
_DEFAULT_DOC_SEARCH_URL = "https://vivado.amd.com/mcp/doc-search"


# Env vars that, if set in the parent shell, force copilot into a
# bring-your-own-key path (often a local llama.cpp / lemonade server).
# Strip them for the test run so copilot uses GitHub-hosted models.
# Set SKILL_TEST_COPILOT_KEEP_BYOK=1 to keep these vars (needed when
# COPILOT_PROVIDER_BASE_URL points at a corporate Azure deployment where
# the model deployment name differs from GitHub-hosted model selectors).
_BYOK_VARS = (
    "COPILOT_PROVIDER_BASE_URL",
    "COPILOT_PROVIDER_API_KEY",
    "COPILOT_PROVIDER_WIRE_API",
    "COPILOT_PROVIDER_MAX_PROMPT_TOKENS",
    "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS",
    "COPILOT_PROVIDER_MODEL",
)


# Token env vars Copilot CLI honours (in order of precedence). If any of
# them is set in the parent shell we KEEP it -- the recommended headless
# auth path is a fine-grained PAT with the `Copilot Requests` permission
# exported as one of these vars. Set SKILL_TEST_COPILOT_STRIP_GH_TOKEN=1
# only if you have an ambient `gh` PAT without Copilot scope and want the
# harness to fall back to the stored OAuth token in ~/.copilot/config.json.
_GH_TOKEN_VARS = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "COPILOT_GITHUB_TOKEN",
)


def _keep_byok() -> bool:
    """Return True if BYOK env vars should be preserved.

    Checked in order:
      1. SKILL_TEST_COPILOT_KEEP_BYOK=1  (env var override, highest priority)
      2. cli_backends.copilot.keep_byok: true  in config.yaml
    """
    if os.environ.get("SKILL_TEST_COPILOT_KEEP_BYOK", "0") == "1":
        return True
    try:
        import yaml
        from skills_testing.core.paths import DEFAULT_CONFIG
        cfg = yaml.safe_load(Path(DEFAULT_CONFIG).read_text()) or {}
        return bool(
            cfg.get("cli_backends", {})
               .get("copilot", {})
               .get("keep_byok", False)
        )
    except Exception:
        return False


class CopilotSkillCLI(SkillCLIBackend):
    name = "copilot"
    binary_env_var = "COPILOT_BIN"
    transcript_format = "copilot_bullets"  # bullet lines (● Read, ● skill(...))

    def _default_binary_lookup(self) -> Optional[str]:
        return shutil.which("copilot")

    def build_command(self, prompt: str, workspace_dir: Path) -> list[str]:
        mcp_cfg_path = workspace_dir / ".copilot" / "mcp-config.json"
        mcp_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_cfg_path.write_text(json.dumps({
            "mcpServers": {
                "vivado-mcp-server": {
                    "type": "http",
                    "url": os.environ.get(
                        "SKILL_TEST_VIVADO_MCP_URL", _DEFAULT_VIVADO_MCP_URL,
                    ),
                },
                "vivado-doc-search": {
                    "type": "http",
                    "url": os.environ.get(
                        "SKILL_TEST_DOC_SEARCH_URL", _DEFAULT_DOC_SEARCH_URL,
                    ),
                },
            }
        }, indent=2))

        cmd = [
            self.binary,
            "-p", prompt,
            "--allow-all-tools",
            "--no-ask-user",
            "--allow-all-paths",
            "--add-dir", str(workspace_dir),
            # NB: we deliberately stay in default text mode here. The JSON
            # envelope (--output-format json) drops Copilot's exit banner,
            # which is the ONLY place Copilot exposes input + cache token
            # counts. Text mode gives us:
            #   <assistant content...>
            #   Changes   +0 -0
            #   Requests  0.33 Premium (4s)
            #   Tokens    ↑ 38.2k • ↓ 53 • 24.2k (cached)
            # which we parse below in parse_token_usage.
            "--log-level", "error",
            "--no-auto-update",
            "--additional-mcp-config", f"@{mcp_cfg_path}",
        ]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def invoke(self, *, prompt: str, workspace_dir: Path,
               timeout_seconds: int, env: Optional[dict] = None) -> dict:
        # NB: ``base.invoke`` does ``os.environ.copy()`` then ``update`` with
        # whatever we pass, so we cannot remove vars by popping them here --
        # we have to override them to empty strings, which Copilot CLI
        # treats as "not set". Default: KEEP shell tokens (recommended PAT
        # path). Opt in to stripping when an ambient non-Copilot PAT is
        # poisoning auth.
        keep_byok = _keep_byok()
        overrides: dict[str, str] = {} if keep_byok else {var: "" for var in _BYOK_VARS}
        if os.environ.get("SKILL_TEST_COPILOT_STRIP_GH_TOKEN", "0") == "1":
            for var in _GH_TOKEN_VARS:
                overrides[var] = ""
        if env:
            overrides.update(env)
        return super().invoke(
            prompt=prompt, workspace_dir=workspace_dir,
            timeout_seconds=timeout_seconds, env=overrides,
        )

    # Banner format (text mode):
    #   Tokens    ↑ 38.2k • ↓ 53 • 24.2k (cached)
    # Numbers are formatted with k/m suffixes (kilo / mega = ×10^3 / ×10^6,
    # not ×1024 — verified empirically against Copilot CLI 1.0.x).
    _TOKENS_RE = re.compile(
        r"Tokens\s+\u2191\s*([\d.]+)\s*([kKmM]?)"
        r"\s*\u2022\s*\u2193\s*([\d.]+)\s*([kKmM]?)"
        r"\s*\u2022\s*([\d.]+)\s*([kKmM]?)\s*\(cached\)"
    )

    @staticmethod
    def _expand(num: str, unit: str) -> int:
        n = float(num)
        scale = {"": 1, "k": 1_000, "K": 1_000,
                 "m": 1_000_000, "M": 1_000_000}.get(unit, 1)
        return int(round(n * scale))

    def parse_token_usage(self, stdout: str, stderr: str) -> Optional[TokenUsage]:
        """Parse Copilot CLI's exit banner (text mode) for token counts.

        Copilot exposes input + cache_read counts only via the human
        banner; ``--output-format json`` drops them entirely (only
        ``premiumRequests`` survives). Cache writes are NOT reported by
        Copilot at all; we leave that field at 0.
        """
        for hay in (stdout, stderr):
            m = self._TOKENS_RE.search(hay)
            if not m:
                continue
            return TokenUsage(
                input=self._expand(m.group(1), m.group(2)),
                output=self._expand(m.group(3), m.group(4)),
                cache_read=self._expand(m.group(5), m.group(6)),
            )
        # Fallback: legacy JSON-envelope path (in case a future Copilot
        # release puts tokens back into --output-format json).
        try:
            obj = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(obj, dict):
            return None
        u = obj.get("usage") or obj.get("message", {}).get("usage") or {}
        return TokenUsage(
            input=int(u.get("input_tokens") or u.get("prompt_tokens") or 0),
            output=int(u.get("output_tokens") or u.get("completion_tokens") or 0),
        )
