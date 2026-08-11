"""
LLM-as-judge support for Skill Testing.

Builds the ``llm_caller`` used by per-case graders that need a frontier-model
opinion -- today, the ``semantic_fields`` comparison in
``graders/output_contract_match.py`` -- dispatched through the AMD LLM
gateway first, then a local CLI binary (opencode/copilot/agent) as fallback.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path


# The skill-test scheduler runs many arms in parallel and each completed run
# fires its own judge call against a single frontier endpoint (azure/gpt-5.4).
# Left unbounded, that burst of concurrent requests gets throttled/queued and
# every call blows past its timeout. This process-wide gate caps how many
# judge calls hit the endpoint at once. It is created lazily and sized from
# config on first use.
_JUDGE_SEMAPHORE: threading.BoundedSemaphore | None = None
_JUDGE_SEM_SIZE: int | None = None
_JUDGE_SEM_LOCK = threading.Lock()

_TRANSIENT_ERROR_MARKERS = (
    "timed out",
    "timeout",
    "rate limit",
    "ratelimit",
    "429",
    "too many requests",
    "overloaded",
    "503",
    "502",
    "connection",
    "temporarily",
)


def _judge_semaphore(max_concurrency: int) -> threading.BoundedSemaphore:
    """Return the shared judge concurrency gate, created once per process.

    The size is fixed on first use; later config changes within the same
    process are ignored so all threads share one consistent gate.
    """
    global _JUDGE_SEMAPHORE, _JUDGE_SEM_SIZE
    with _JUDGE_SEM_LOCK:
        if _JUDGE_SEMAPHORE is None:
            _JUDGE_SEM_SIZE = max(1, int(max_concurrency))
            _JUDGE_SEMAPHORE = threading.BoundedSemaphore(_JUDGE_SEM_SIZE)
        return _JUDGE_SEMAPHORE


def _is_transient_error(error: str | None) -> bool:
    """True if a judge error looks like a timeout / throttling / transient fault."""
    if not error:
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in _TRANSIENT_ERROR_MARKERS)


# A judge that answered with narration instead of JSON on one attempt often
# returns a clean grade on the next, so parse failures are retryable too.
_PARSE_FAILURE_MARKER = "could not parse judge json"


def _is_retryable_error(error: str | None) -> bool:
    """True for transient faults *and* judge-JSON parse failures.

    Both are worth another attempt rather than being scored as an immediate F.
    """
    if not error:
        return False
    if _is_transient_error(error):
        return True
    return _PARSE_FAILURE_MARKER in error.lower()


def _env_flag(name: str) -> bool | None:
    """Interpret an env var as a boolean flag; None when unset/empty."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _resolve_gateway_cfg(gateway_cfg: dict | None) -> dict:
    """Overlay environment variables onto the judge gateway config.

    Lets the Anthropic-compatible gateway be enabled and configured without
    editing ``config.yaml``. Each env var overrides the matching config key:

      LLM_GATEWAY_ENABLED, LLM_GATEWAY_BASE_URL, LLM_GATEWAY_SUBSCRIPTION_KEY,
      LLM_GATEWAY_API_KEY, LLM_GATEWAY_MODEL, LLM_GATEWAY_MAX_TOKENS.

    As a convenience, credentials present in the environment
    (``ANTHROPIC_API_KEY`` or ``LLM_GATEWAY_SUBSCRIPTION_KEY``) auto-enable the
    gateway unless ``LLM_GATEWAY_ENABLED`` is explicitly set to a falsey value.
    """
    resolved = dict(gateway_cfg or {})

    for env_name, key in (
        ("LLM_GATEWAY_BASE_URL", "base_url"),
        ("LLM_GATEWAY_SUBSCRIPTION_KEY", "subscription_key"),
        ("LLM_GATEWAY_API_KEY", "api_key"),
        ("LLM_GATEWAY_MODEL", "model"),
    ):
        val = os.environ.get(env_name)
        if val:
            resolved[key] = val

    max_tokens_env = os.environ.get("LLM_GATEWAY_MAX_TOKENS")
    if max_tokens_env:
        try:
            resolved["max_tokens"] = int(max_tokens_env)
        except ValueError:
            pass

    enabled_flag = _env_flag("LLM_GATEWAY_ENABLED")
    if enabled_flag is not None:
        resolved["enabled"] = enabled_flag
    elif os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "LLM_GATEWAY_SUBSCRIPTION_KEY"
    ):
        resolved["enabled"] = True

    return resolved


def _dispatch_raw(
    prompt: str,
    *,
    judge_model: str,
    gateway_cfg: dict,
    timeout: int,
) -> tuple[str | None, str | None]:
    """Send *prompt* to the judge endpoint and return ``(text, error)``.

    Exactly one of the pair is non-None. Tries the AMD LLM gateway first
    (when enabled) and falls back to a local CLI binary — the same dispatch
    order the Answer Quality judge uses. Returns raw model text; parsing is
    the caller's job.
    """
    gateway_cfg = _resolve_gateway_cfg(gateway_cfg)

    # -- Gateway (Anthropic-compatible API) -------------------------------
    if gateway_cfg.get("enabled", False):
        try:
            from anthropic import Anthropic

            base_url = gateway_cfg.get("base_url", "")
            subscription_key = gateway_cfg.get("subscription_key", "")
            anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if anthropic_key:
                client = Anthropic(api_key=anthropic_key, timeout=float(timeout))
            elif subscription_key:
                try:
                    user_login = os.getlogin()
                except OSError:
                    user_login = os.environ.get("USER", "unknown")
                client = Anthropic(
                    base_url=base_url,
                    api_key=gateway_cfg.get("api_key", "dummy"),
                    default_headers={
                        "Ocp-Apim-Subscription-Key": subscription_key,
                        "user": user_login,
                        "anthropic-version": "2023-10-16",
                    },
                    timeout=float(timeout),
                )
            else:
                client = None
            if client is not None:
                resp = client.messages.create(
                    model=gateway_cfg.get("model", judge_model),
                    max_tokens=int(gateway_cfg.get("max_tokens", 1024)),
                    temperature=0.0,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text, None
        except Exception as exc:  # fall through to the CLI path
            gateway_err = f"gateway call failed: {exc}"
        else:
            gateway_err = None
    else:
        gateway_err = None

    # -- Local CLI binary (opencode / copilot / agent) --------------------
    try:
        import subprocess
        import sys as _sys

        _tests_dir = str(Path(__file__).resolve().parents[3] / "tests")
        if _tests_dir not in _sys.path:
            _sys.path.insert(0, _tests_dir)
        from test_answer_quality import (  # type: ignore
            _extract_cli_answer_text,
            _find_judge_bin,
        )

        judge_bin = _find_judge_bin()
        if not judge_bin:
            return None, gateway_err or "judge binary not found (opencode/copilot/agent)"

        bin_name = Path(judge_bin).name
        proc_env: dict | None = None
        if bin_name == "opencode":
            cmd = [judge_bin, "run", prompt, "--model", judge_model]
            # TEMP: per-call OPENCODE_DB isolation removed to reproduce
            # fixes/01-llm-judge-database-file.md. Restore before merging.
        elif bin_name == "agent":
            # Cursor's default text mode streams agentic narration instead of
            # the requested JSON, and --force stops it stalling on approval
            # prompts. Request a structured envelope and unwrap it below.
            cmd = [judge_bin, "-p", "--output-format", "json", "--force",
                   "--model", judge_model, prompt]
        else:  # copilot
            cmd = [judge_bin, "-p", prompt, "-s", "--model", judge_model,
                   "--no-ask-user"]

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, env=proc_env,
        )
        if proc.returncode != 0:
            return None, (proc.stderr.strip() or f"exit code {proc.returncode}")
        return _extract_cli_answer_text(bin_name, proc.stdout), None
    except subprocess.TimeoutExpired:
        return None, f"judge timed out after {timeout}s"
    except Exception as exc:
        return None, str(exc)


def make_llm_caller(config: dict | None):
    """Build an ``llm_caller(prompt) -> {"score", "rationale"}`` for the
    ``llm_judge`` grader, or ``None`` when no judge is configured.

    The ``llm_judge`` grader (``graders._builtins.LLMJudge``) hands us a
    prompt that already asks the model to reply with
    ``{"score": float, "rationale": str}`` JSON. We dispatch it through the
    same endpoint the Answer Quality judge uses (gateway first, then a local
    CLI), parse the JSON out of the reply, and clamp the score to [0, 1].
    Transient (timeout/throttle) failures are retried with backoff and the
    process-wide concurrency gate caps simultaneous calls.
    """
    cfg = config or {}
    judge_cfg = (cfg.get("skill_testing", {}) or {}).get("llm_judge", {}) or {}
    # No judge configured -> let the grader report "no llm_caller".
    if not judge_cfg.get("enabled"):
        return None

    judge_model = judge_cfg.get("model", "azure/gpt-5.4")
    gateway_cfg = judge_cfg.get("gateway", {}) or {}
    timeout = int(judge_cfg.get("timeout_seconds", 180))
    max_concurrency = int(judge_cfg.get("max_concurrency", 2))
    max_retries = int(judge_cfg.get("max_retries", 2))
    backoff_base = float(judge_cfg.get("retry_backoff_seconds", 5))

    def _call(prompt: str) -> dict:
        import sys as _sys
        _tests_dir = str(Path(__file__).resolve().parents[3] / "tests")
        if _tests_dir not in _sys.path:
            _sys.path.insert(0, _tests_dir)
        try:
            from test_answer_quality import _parse_judge_json, _debug_snippet  # type: ignore
        except Exception as exc:
            return {"score": 0.0, "rationale": f"judge import failed: {exc}"}

        gate = _judge_semaphore(max_concurrency)
        last_err = "unknown judge error"
        for attempt in range(max_retries + 1):
            # Hold the gate only while the request is in flight; release it
            # during backoff so a sleeping retry frees a concurrency slot.
            with gate:
                text, err = _dispatch_raw(
                    prompt,
                    judge_model=judge_model,
                    gateway_cfg=gateway_cfg,
                    timeout=timeout,
                )
            if text is not None:
                parsed = _parse_judge_json(text)
                if parsed is not None:
                    try:
                        score = float(parsed.get("score", 0.0))
                    except (TypeError, ValueError):
                        score = 0.0
                    # Clamp low at 0 but leave the upper bound wide enough for
                    # both the 0-1 and 0-100 rubric scales; the grader decides
                    # how to interpret and normalise the value.
                    score = max(0.0, min(100.0, score))
                    return {"score": score,
                            "rationale": str(parsed.get("rationale", ""))}
                # No JSON in the reply (often a CLI agent that narrated
                # instead of answering) -- retryable rather than an instant F.
                last_err = (f"could not parse judge JSON from response: "
                            f"{_debug_snippet(text)}")
            else:
                last_err = err or "unknown judge error"
            if not _is_retryable_error(last_err):
                break
            if attempt < max_retries:
                time.sleep(backoff_base * (2 ** attempt))
        return {"score": 0.0, "rationale": f"judge error: {last_err}"}

    return _call
