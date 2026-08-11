"""
Subprocess implementation of the backend contract, plus the null fallback.

``interface.SkillBackend`` declares *what* every backend must provide;
``SkillCLIBackend`` here implements the parts shared by everything that
drives a real agent CLI as a child process:

  * binary discovery (config ``bin_path`` > env var > PATH/well-known dirs)
  * streamed stdout/stderr capture with per-line arrival timestamps
  * timeout handling that yields ``exit_code 124`` plus partial output
  * tool-call timeline reconstruction and final-response extraction
  * token accounting assembled from the backend's ``parse_token_usage``

A concrete backend therefore declares only what differs: ``build_command``,
``_default_binary_lookup``, its ``parse_token_usage``, and any env or
preflight quirks.

Backends are *workspace-aware*: they run with cwd set to ``workspace_dir``
so any ``.claude/``, ``.cursor/``, or ``.opencode/`` subdirectory there is
auto-discovered as the project root for skills, settings, and MCP overrides.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from abc import abstractmethod
from pathlib import Path
from typing import Optional

from .interface import (
    InvokeResult,
    SkillBackend,
    TokenUsage,
    _SKILL_INVOKE_PATTERNS,
    _SKILL_NAME_PATTERN,
)

# Re-exported for callers that import the detection regexes directly
# (tests/test_skill_detection.py exercises them without a backend instance).
__all__ = [
    "SkillCLIBackend", "NullSkillCLI", "InvokeResult", "SkillBackend",
    "TokenUsage", "_SKILL_INVOKE_PATTERNS", "_SKILL_NAME_PATTERN",
]


# ---------------- subprocess base ---------------------------------------


class SkillCLIBackend(SkillBackend):
    """Base class for backends that drive an agent CLI as a subprocess."""

    def __init__(self, model: str, *, bin_path: Optional[str] = None) -> None:
        self.model = model
        self._config_bin_path = bin_path
        self.binary = self._find_binary()
        if not self.binary:
            raise RuntimeError(
                f"{self.name}: binary not found "
                f"(set cli_backends.{self.name}.bin_path in config.yaml, "
                f"{self.binary_env_var}, or put it on PATH)"
            )

    # ---- execution ----------------------------------------------------

    @abstractmethod
    def build_command(self, prompt: str, workspace_dir: Path) -> list[str]:
        """Return the argv for a non-interactive invocation."""

    def invoke(
        self, *, prompt: str, workspace_dir: Path,
        timeout_seconds: int, env: Optional[dict] = None,
    ) -> dict:
        spawn_env = os.environ.copy()
        if env:
            spawn_env.update(env)
        cmd = self.build_command(prompt, Path(workspace_dir))
        (stdout, stderr, rc, elapsed,
         stdout_stamps, stderr_stamps) = self._run_streamed(
            cmd, workspace_dir, spawn_env, prompt, timeout_seconds,
        )

        return InvokeResult.from_usage(
            stdout=stdout, stderr=stderr, exit_code=rc, wall_clock_s=elapsed,
            usage=self.token_usage(stdout, stderr),
            vivado_session_ids=self.extract_vivado_session_ids(stdout, stderr),
            tool_timeline=self._build_timeline(
                stdout_stamps, stderr_stamps, elapsed),
            final_response=self._extract_final_response(stdout, stderr),
        ).as_dict()

    def _build_timeline(
        self, stdout_stamps: list, stderr_stamps: list, elapsed: float,
    ) -> list[dict]:
        """Chronological tool-call timeline (name + duration per call), built
        from the per-line arrival timestamps recorded while streaming.

        Never fatal: a transcript we can't parse costs a timeline, not a run.
        """
        try:
            from .tool_timing import build_tool_timeline
            return build_tool_timeline(
                stdout_stamps, stderr_stamps,
                client=self.name,
                transcript_format=self.transcript_format,
                total_wall_s=elapsed,
            )
        except Exception:
            return []

    def _extract_final_response(self, stdout: str, stderr: str) -> str:
        """The agent's final answer text, taken from the FULL stdout.

        Done here rather than at grade time because the session log truncates
        stdout and can drop the final message at the end of a long transcript.
        """
        try:
            from ..graders.trace import final_response_text
            return final_response_text(
                stdout, stderr, transcript_format=self.transcript_format)
        except Exception:
            return ""

    def _run_streamed(
        self, cmd: list[str], workspace_dir, spawn_env: dict,
        prompt: str, timeout_seconds: int,
    ) -> tuple[str, str, int, float, list, list]:
        """Run ``cmd`` capturing stdout/stderr line-by-line with a monotonic
        arrival offset per line, so tool-call timing can be reconstructed.

        Returns ``(stdout, stderr, returncode, elapsed_s, stdout_stamps,
        stderr_stamps)`` where each ``*_stamps`` is a list of
        ``(offset_seconds, line_without_newline)``. Full text is preserved;
        a timeout yields rc=124 with a marker appended to stderr.
        """
        uses_stdin = self._uses_stdin_prompt()
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        stdout_stamps: list[tuple[float, str]] = []
        stderr_stamps: list[tuple[float, str]] = []
        mono0 = time.monotonic()

        def _reader(stream, text_sink, stamp_sink):
            try:
                for line in iter(stream.readline, ""):
                    off = time.monotonic() - mono0
                    text_sink.append(line)
                    stamp_sink.append((off, line.rstrip("\n")))
            except (ValueError, OSError):
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        proc = subprocess.Popen(
            cmd,
            cwd=str(workspace_dir),
            env=spawn_env,
            stdin=subprocess.PIPE if uses_stdin else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        t_out = threading.Thread(
            target=_reader, args=(proc.stdout, stdout_lines, stdout_stamps),
            daemon=True)
        t_err = threading.Thread(
            target=_reader, args=(proc.stderr, stderr_lines, stderr_stamps),
            daemon=True)
        t_out.start()
        t_err.start()

        if uses_stdin and proc.stdin is not None:
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        timed_out = False
        try:
            rc = proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            proc.wait()
            rc = 124

        # Reader threads drain the pipes to EOF once the process exits.
        t_out.join(timeout=10)
        t_err.join(timeout=10)

        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
        if timed_out:
            stderr += f"\n[skills_testing] timed out after {timeout_seconds}s\n"
        elapsed = time.monotonic() - mono0
        return stdout, stderr, rc, elapsed, stdout_stamps, stderr_stamps

    def _uses_stdin_prompt(self) -> bool:
        return False

    # ---- binary discovery ---------------------------------------------

    def _find_binary(self) -> Optional[str]:
        # config.yaml (cli_backends.<name>.bin_path) beats an env var beats
        # PATH/well-known-dir search -- same precedence workspace_root uses.
        if self._config_bin_path and Path(self._config_bin_path).exists():
            return self._config_bin_path
        if self.binary_env_var:
            override = os.environ.get(self.binary_env_var)
            if override and Path(override).exists():
                return override
        return self._default_binary_lookup()

    @abstractmethod
    def _default_binary_lookup(self) -> Optional[str]:
        """Search PATH and well-known install dirs for this CLI."""

    # ---- deprecated token-stat shims ----------------------------------
    #
    # Pre-interface names. ``parse_token_usage`` is the override point now;
    # these remain for external callers and tests that predate it.

    def _parse_usage_extended(self, stdout: str, stderr: str) -> dict[str, int]:
        """Deprecated: use ``token_usage``. Returns the four-key dict."""
        return self.token_usage(stdout, stderr).as_dict()

    def _parse_usage(self, stdout: str, stderr: str) -> tuple[int, int]:
        """Deprecated: use ``token_usage``. Returns ``(input, output)``."""
        return self.token_usage(stdout, stderr).as_tuple()

    def _extract_vivado_session_ids(self, stdout: str, stderr: str) -> list[str]:
        """Deprecated: use ``extract_vivado_session_ids``."""
        return self.extract_vivado_session_ids(stdout, stderr)


# ---------------- null fallback -----------------------------------------


class NullSkillCLI(SkillBackend):
    """Stand-in used when a real backend can't be constructed.

    Implements the same interface rather than duck-typing a subset, so the
    runner can branch on ``is_available`` and every consumer still gets a
    complete ``InvokeResult`` dict (previously this returned a partial dict
    missing the cache-token, timeline, and final-response keys).
    """

    def __init__(self, name: str, model: str, reason: str = "") -> None:
        self.name = name
        self.model = model
        self.reason = reason or "no backend wired up"

    @property
    def is_available(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str:
        return self.reason

    def invoke(self, *, prompt: str = "", workspace_dir: Path = None,
               timeout_seconds: int = 0, env: Optional[dict] = None) -> dict:
        return InvokeResult(
            stdout="", stderr=f"[NullSkillCLI] {self.reason}",
            exit_code=127, wall_clock_s=0.0,
        ).as_dict()

    def detect_skill_invocation(self, *_a) -> tuple[bool, list[str]]:
        return False, []

    def hide_skills_env_overrides(self) -> Optional[dict]:
        return None
