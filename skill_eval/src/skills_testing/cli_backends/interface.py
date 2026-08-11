"""
The backend contract: ``SkillBackend``.

Every agent CLI the harness can drive -- and the ``NullSkillCLI`` stand-in
used when one isn't installed -- implements this single interface. It is the
*whole* surface the runner, the graders, and the workspace stager are allowed
to rely on; nothing outside this package should reach past it.

The contract has five parts:

1. **Identity / capability declaration** -- class attributes read off the
   *class*, never an instance (``name``, ``transcript_format``,
   ``workspace_skills_dir``, ``binary_env_var``). They must stay
   instantiation-free: the workspace is staged and transcripts are graded on
   hosts where the CLI binary is absent and no instance can be built.
2. **Availability** -- ``is_available`` / ``unavailable_reason``, so the
   runner can record a SKIPPED row instead of type-testing for a stand-in.
3. **Execution** -- ``build_command`` and ``invoke``. ``invoke`` returns the
   flat dict described by ``InvokeResult`` and never raises on timeout: it
   reports ``exit_code == 124`` with whatever partial output it captured.
4. **Token statistics** -- ``parse_token_usage`` is the single per-backend
   override point; ``token_usage`` is the resolved accessor that applies the
   shared regex/heuristic fallback. Backends do not reimplement the fallback.
5. **Observability and A/B hooks** -- ``detect_skill_invocation``,
   ``hide_skills_env_overrides``, ``extract_vivado_session_ids``,
   ``preflight_skip``.

Only ``invoke`` is abstract. Everything else has a working default, so a
backend (or a test double) declares just the behaviour that differs from the
shared implementation in ``base.SkillCLIBackend``.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------- token statistics --------------------------------------


# Chars-per-token divisors for the last-resort estimate. Deliberately crude:
# a transcript we couldn't parse carries no usage signal at all, so a simple
# ratio beats reverse-engineering a vendor's tokenizer. Anything produced
# this way is flagged ``estimated=True`` so callers can tell it apart from a
# real vendor-reported count.
_EST_CHARS_PER_INPUT_TOKEN = 4
_EST_CHARS_PER_OUTPUT_TOKEN = 7


# Generic usage envelopes, tried before falling back to the char estimate.
# Ordered most- to least-specific; the first match wins.
_GENERIC_USAGE_PATTERNS = (
    re.compile(
        r'"input_tokens"\s*:\s*(\d+).*?"output_tokens"\s*:\s*(\d+)',
        re.DOTALL,
    ),
    re.compile(
        r'"prompt_tokens"\s*:\s*(\d+).*?"(?:completion|output)_tokens"\s*:\s*(\d+)',
        re.DOTALL,
    ),
)


@dataclass
class TokenUsage:
    """Token accounting for one invocation.

    ``cache_read``/``cache_write`` are Anthropic-style prompt-cache counts,
    kept separate from live input/output because ``core.cost_model`` prices
    them at different rates (read ~10% of input, write ~125%). A provider
    that doesn't report them leaves them at 0 rather than folding them into
    ``input`` -- folding would silently overbill the row.
    """

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    # True when these numbers came from the char-count heuristic rather than
    # a vendor-reported usage block. Never persisted; used for diagnostics.
    estimated: bool = False

    @property
    def total(self) -> int:
        """Live tokens only -- cache traffic is billed separately."""
        return self.input + self.output

    def is_empty(self) -> bool:
        return not (self.input or self.output
                    or self.cache_read or self.cache_write)

    def as_tuple(self) -> tuple[int, int]:
        return self.input, self.output

    def as_dict(self) -> dict[str, int]:
        return {"input": self.input, "output": self.output,
                "cache_read": self.cache_read, "cache_write": self.cache_write}


@dataclass
class InvokeResult:
    """The full result of one CLI invocation.

    ``as_dict()`` is the wire format the runner and graders consume; every
    implementation of ``SkillBackend.invoke`` returns that dict (never a
    partial one), so downstream code can index keys without ``.get`` guards.
    """

    stdout: str
    stderr: str
    exit_code: int
    wall_clock_s: float
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    # Anthropic-style prompt-cache tokens. Cursor and Claude Code report
    # these separately from live input/output; cost_model.compute_cost
    # prices them at the cache rates (read ~10% of input, write ~125%).
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    vivado_session_ids: Optional[list[str]] = None
    # Ordered [{seq, name, args, t_start, duration_s}] recovered from the
    # timestamped transcript -- the chronological chain of tool calls and how
    # long each took. Empty when the backend transcript carries no tool signal.
    tool_timeline: Optional[list[dict]] = None
    # The agent's final answer text (not the raw transcript). Extracted from
    # the FULL stdout, since the session log truncates stdout and can drop
    # the final message that lives at the very end of a long transcript.
    final_response: str = ""

    @classmethod
    def from_usage(cls, *, stdout: str, stderr: str, exit_code: int,
                   wall_clock_s: float, usage: TokenUsage,
                   vivado_session_ids: Optional[list[str]] = None,
                   tool_timeline: Optional[list[dict]] = None,
                   final_response: str = "") -> "InvokeResult":
        """Build a result from a ``TokenUsage``, deriving ``total_tokens``."""
        return cls(
            stdout=stdout, stderr=stderr, exit_code=exit_code,
            wall_clock_s=wall_clock_s,
            prompt_tokens=usage.input, output_tokens=usage.output,
            total_tokens=usage.total,
            cache_read_tokens=usage.cache_read,
            cache_write_tokens=usage.cache_write,
            vivado_session_ids=vivado_session_ids,
            tool_timeline=tool_timeline,
            final_response=final_response,
        )

    def as_dict(self) -> dict:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "wall_clock_s": self.wall_clock_s,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "vivado_session_ids": self.vivado_session_ids or [],
            "tool_timeline": self.tool_timeline or [],
            "final_response": self.final_response or "",
        }


# ---------------- skill-activation detection ----------------------------


_SKILL_INVOKE_PATTERNS = [
    # Claude Code stream-json: tool_use { "name": "Skill", ... } or
    # text mentions of "Reading SKILL.md" / "applying skill X".
    re.compile(r'"name"\s*:\s*"Skill"', re.IGNORECASE),
    re.compile(r'invoking\s+skill[:\s]+([A-Za-z0-9_\-/]+)', re.IGNORECASE),
    re.compile(r'applying\s+the\s+([A-Za-z0-9_\-/]+)\s+skill', re.IGNORECASE),
    re.compile(r'using\s+the\s+([A-Za-z0-9_\-/]+)\s+skill', re.IGNORECASE),
    re.compile(r'Read[a-z ]*SKILL\.md', re.IGNORECASE),
    # A staged skill body being read, from any client's skill root
    # (.claude/skills for Claude Code/Copilot, .opencode/skills for
    # opencode). Kept path-prefix-agnostic so a folder rename per client
    # doesn't silently drop detection.
    re.compile(
        r'\.(?:claude|opencode)/skills/([A-Za-z0-9_\-/]+)/SKILL\.md',
        re.IGNORECASE,
    ),
    # Cursor Agent: reads skills from .cursor/rules/ or references skill paths
    re.compile(r'\.cursor/skills/([A-Za-z0-9_\-/]+)/SKILL\.md', re.IGNORECASE),
    # opencode's own skill-tool markers (verified in run transcripts): it
    # loads a skill via a dedicated tool and logs the load/permission grant
    # rather than reading the SKILL.md path inline the way Claude Code does.
    re.compile(r'Loaded\s+skill:\s*([A-Za-z0-9_\-/]+)', re.IGNORECASE),
    re.compile(r'<skill_content\s+name="([A-Za-z0-9_\-/]+)"', re.IGNORECASE),
    re.compile(r'permission=skill\s+pattern=([A-Za-z0-9_\-/]+)', re.IGNORECASE),
    re.compile(r'follow.*skill.*instructions', re.IGNORECASE),
    re.compile(r'skill[:\s]+rtl[_-]', re.IGNORECASE),
]

# Skill names extracted from a staged-skill path, any client's skill root.
_SKILL_NAME_PATTERN = re.compile(
    r'\.(?:claude|opencode)/skills/([A-Za-z0-9_\-/]+)/SKILL\.md', re.IGNORECASE
)


# Vivado MCP session ids appearing anywhere in a transcript.
_SESSION_ID_PATTERNS = (
    re.compile(r'"session_id"\s*:\s*"([^"]+)"'),
    re.compile(r'session[_\- ]?id[=:\s]+([A-Za-z0-9_\-]+)'),
)

# A real Vivado MCP session id is always minted by the server as
# ``vivado-<8-digit date>-<6-digit time>`` (e.g. ``vivado-20260731-103759``);
# nothing else is. Some tools (e.g. ``vivado_history``) accept keyword values
# like "all" in their own ``session_id`` argument -- meaning "every session",
# not a real one -- and some CLI backends (e.g. Cursor) stamp an unrelated
# ``session_id`` field of their own (a bare UUID identifying the CLI's own
# conversation, not any Vivado session) on transcript events. A plain
# "contains a digit" check can't tell either of those apart from a genuine
# session reference -- a UUID has digits too.
#
# The full ``\d{8}-\d{6}`` shape (not just the ``vivado-`` prefix) also
# matters for a subtler reason: a streaming CLI backend (e.g. Claude Code's
# ``stream-json`` output) emits the model's answer as many incremental
# partial-JSON chunks, so a session id the model quotes in its own output
# text can appear character-by-character across several transcript lines.
# Regex-scanning the raw transcript can match a mid-stream fragment like
# ``vivado-20260`` alongside the complete ``vivado-20260803-131158`` -- and
# since a prefix always sorts before the string it's a prefix of, a
# sort-then-take-first pick would silently prefer the truncated fragment.
# Requiring the full, fixed-width shape rejects any such partial fragment
# (it can never happen to have exactly 8+6 digits by accident at every
# possible chunk boundary), without having to enumerate every backend's own
# streaming format.
_SESSION_ID_LOOKS_REAL = re.compile(r'^vivado-\d{8}-\d{6}$')


# ---------------- the interface ------------------------------------------


class SkillBackend(ABC):
    """The contract every skill-test backend implements.

    Subclass ``base.SkillCLIBackend`` for anything that drives a real CLI
    subprocess -- it supplies binary discovery, streamed capture, tool-call
    timing, and final-response extraction on top of this interface. Subclass
    ``SkillBackend`` directly only for something that is *not* a subprocess:
    the ``NullSkillCLI`` stand-in, and test doubles.
    """

    # ---- 1. identity / capability declaration -------------------------
    #
    # Read off the CLASS, never an instance: the workspace is staged before
    # any backend object exists, and grading runs on hosts with no CLI
    # binary installed (where construction raises).

    #: Registry key for this backend, e.g. ``"claude_code"``.
    name: str = ""
    #: Env var that overrides binary discovery, e.g. ``"CLAUDE_CODE_BIN"``.
    binary_env_var: str = ""
    #: Transcript dialect this backend emits, consumed by ``graders.trace``
    #: to pick the right tool-call parser. ``""`` means "auto-detect".
    #: Recognized: ``anthropic_stream_json``, ``opencode_logs``,
    #: ``copilot_bullets``, ``cursor_json``.
    transcript_format: str = ""
    #: Workspace-relative directory where this client's skill tree is staged
    #: (and where the client discovers it). Claude Code and Copilot walk
    #: ``.claude/skills``; opencode walks ``.opencode/skills``.
    workspace_skills_dir: str = ".claude/skills"

    #: Short model selector passed to the CLI. Set by ``__init__``.
    model: str = ""

    # ---- 2. availability ----------------------------------------------

    @property
    def is_available(self) -> bool:
        """False when this backend cannot actually run a case.

        The runner records a SKIPPED row (with ``unavailable_reason``)
        instead of invoking. Real backends raise at construction when their
        binary is missing, so an instance that exists is available; the
        ``NullSkillCLI`` stand-in overrides this to False.
        """
        return True

    @property
    def unavailable_reason(self) -> str:
        """Why ``is_available`` is False; ``""`` when it is True."""
        return ""

    # ---- 3. execution -------------------------------------------------

    def build_command(self, prompt: str, workspace_dir: Path) -> list[str]:
        """Return the argv for a non-interactive invocation.

        Subprocess backends must override this (``base.SkillCLIBackend``
        declares it abstract). Non-subprocess implementations have no argv
        and inherit the empty default.
        """
        return []

    @abstractmethod
    def invoke(
        self, *, prompt: str, workspace_dir: Path,
        timeout_seconds: int, env: Optional[dict] = None,
    ) -> dict:
        """Run the agent against ``workspace_dir`` and return
        ``InvokeResult.as_dict()``.

        Must NOT raise on timeout -- return ``exit_code == 124`` with the
        partial output captured so far, which is what lets the runner's
        retry loop reuse the Vivado session the killed attempt created.
        """

    # ---- 4. token statistics ------------------------------------------

    def parse_token_usage(self, stdout: str, stderr: str) -> Optional[TokenUsage]:
        """Per-backend usage parser -- **the** override point for token stats.

        Return ``None`` (or an empty ``TokenUsage``) when the transcript
        carries no usage signal; ``token_usage`` then applies the shared
        fallback. Never call the fallback yourself, and never call
        ``token_usage`` from here: that is what made the old
        ``_parse_usage``/``_parse_usage_extended`` pair mutually recursive
        and forced every backend to inline a duplicate of its own parser.
        """
        return None

    def token_usage(self, stdout: str, stderr: str) -> TokenUsage:
        """Resolved token counts: this backend's parser, else the fallback."""
        usage = self.parse_token_usage(stdout, stderr)
        if usage is not None and not usage.is_empty():
            return usage
        return self.default_token_usage(stdout, stderr)

    def default_token_usage(self, stdout: str, stderr: str) -> TokenUsage:
        """Backend-agnostic fallback: generic usage envelope, else estimate.

        Tries the common ``input_tokens``/``prompt_tokens`` JSON shapes that
        most providers emit somewhere in a transcript, then gives up and
        estimates from character counts.
        """
        for pattern in _GENERIC_USAGE_PATTERNS:
            for hay in (stdout, stderr):
                match = pattern.search(hay)
                if not match:
                    continue
                try:
                    return TokenUsage(input=int(match.group(1)),
                                      output=int(match.group(2)))
                except ValueError:
                    continue
        return self.estimate_token_usage(stdout, stderr)

    def estimate_token_usage(self, stdout: str, stderr: str) -> TokenUsage:
        """Last-resort char-count estimate, flagged ``estimated=True``."""
        return TokenUsage(
            input=len(stdout) // _EST_CHARS_PER_INPUT_TOKEN,
            output=len(stdout) // _EST_CHARS_PER_OUTPUT_TOKEN,
            estimated=True,
        )

    # ---- 5. observability and A/B hooks -------------------------------

    def detect_skill_invocation(
        self, stdout: str, stderr: str,
    ) -> tuple[bool, list[str]]:
        """Whether a skill actually activated, and which ones.

        Drives the A/B contract: the no-skill arm is only trustworthy if we
        can show the with-skill arm really loaded the skill. The default
        regex sweep covers every client's markers; override only if a client
        signals activation in a way the shared patterns miss.
        """
        names: set[str] = set()
        for hay in (stdout, stderr):
            invoked = any(pat.search(hay) for pat in _SKILL_INVOKE_PATTERNS)
            for match in _SKILL_NAME_PATTERN.finditer(hay):
                names.add(match.group(1))
            if invoked or names:
                return True, sorted(names)
        return False, sorted(names)

    def hide_skills_env_overrides(self) -> Optional[dict]:
        """Env overrides that blind this client to every skill tree.

        Produces the no-skill A/B arm. Returning ``{}`` means "no env
        override needed" (the client only reads workspace-local skills, and
        the runner simply doesn't stage them). Returning ``None`` means
        "no recipe" and lets the runner fall back to ``runtime.skill_hider``.
        """
        from ..runtime.skill_hider import hide_skills_env
        return hide_skills_env(self.name) or None

    def extract_vivado_session_ids(self, stdout: str, stderr: str) -> list[str]:
        """Vivado MCP session ids this invocation touched.

        The runner carries these across a retry so a timed-out attempt's
        Vivado work isn't orphaned, and hands them to ``cleanup_manager``.
        """
        ids: set[str] = set()
        for hay in (stdout, stderr):
            for pattern in _SESSION_ID_PATTERNS:
                for match in pattern.finditer(hay):
                    sid = match.group(1)
                    if _SESSION_ID_LOOKS_REAL.search(sid):
                        ids.add(sid)
        return sorted(ids)

    def preflight_skip(
        self, *, prompt: str, workspace_dir: Path, timeout_seconds: int,
    ) -> Optional[str]:
        """Optional pre-invocation throughput check.

        Backends backed by a slow on-prem inference engine should override
        this to probe the model's prompt-eval rate and return a short
        ``"<reason>"`` string when the test prompt cannot reasonably finish
        within ``timeout_seconds``. The runner records a SKIPPED row with
        the returned reason instead of waiting out the timeout. Returning
        ``None`` (the default) means "go ahead and invoke".
        """
        return None


__all__ = ["SkillBackend", "InvokeResult", "TokenUsage"]
