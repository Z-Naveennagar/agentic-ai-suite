"""Unit tests for opencode preflight throughput probe (Fix #2)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from skills_testing.cli_backends.opencode import OpencodeSkillCLI


@pytest.fixture(autouse=True)
def _enable_preflight(monkeypatch):
    """Preflight is opt-in (default off so on-prem models run to
    completion). The unit tests cover the *enabled* code path, so flip
    the env var on for the duration of every test in this module."""
    monkeypatch.setenv("SKILL_TEST_ENABLE_PREFLIGHT", "1")


def _make_ws(tmp_path: Path, total_bytes: int) -> Path:
    """Create a workspace with a single .md file of approx total_bytes."""
    skills = tmp_path / ".claude" / "skills" / "demo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("x" * total_bytes)
    return tmp_path


@pytest.fixture
def opencode_cli(monkeypatch):
    """Build OpencodeSkillCLI without requiring the real binary."""
    monkeypatch.setattr(OpencodeSkillCLI, "_find_binary", lambda self: "/bin/true")
    def _make(model: str) -> OpencodeSkillCLI:
        return OpencodeSkillCLI(model)
    return _make


def test_preflight_returns_none_for_non_lemonade_provider(tmp_path, opencode_cli):
    cli = opencode_cli("openai/gpt-4o")
    assert cli.preflight_skip(prompt="hi", workspace_dir=tmp_path,
                              timeout_seconds=600) is None


def test_preflight_returns_none_for_small_prompts(tmp_path, opencode_cli):
    cli = opencode_cli("lemonade/Gemma-4-26B-A4B-it-GGUF")
    # Tiny prompt + empty workspace = ~0 tokens; no probe attempted.
    with patch.object(OpencodeSkillCLI, "_probe_prompt_per_second") as p:
        result = cli.preflight_skip(prompt="hi", workspace_dir=tmp_path,
                                    timeout_seconds=600)
    assert result is None
    p.assert_not_called()


def test_preflight_skips_when_model_too_slow(tmp_path, opencode_cli):
    # 200 KB workspace / 3.5 chars-per-token ~= 57k tokens
    ws = _make_ws(tmp_path, 200_000)
    cli = opencode_cli("lemonade/Gemma-4-26B-A4B-it-GGUF")
    # 50 tok/s * 600s budget * 0.7 = 21000 tokens we could ingest;
    # 57k > 21k, so skip.
    with patch.object(OpencodeSkillCLI, "_probe_prompt_per_second",
                      return_value=50.0):
        reason = cli.preflight_skip(prompt="", workspace_dir=ws,
                                    timeout_seconds=600)
    assert reason is not None
    assert "model_too_slow_for_prompt" in reason
    assert "tok/s" in reason


def test_preflight_passes_when_model_fast_enough(tmp_path, opencode_cli):
    ws = _make_ws(tmp_path, 200_000)  # ~57k tokens
    cli = opencode_cli("lemonade/Gemma-4-26B-A4B-it-GGUF")
    # 1000 tok/s * 0.7 * 600s = 420k token budget; 57k well under.
    with patch.object(OpencodeSkillCLI, "_probe_prompt_per_second",
                      return_value=1000.0):
        assert cli.preflight_skip(prompt="", workspace_dir=ws,
                                  timeout_seconds=600) is None


def test_preflight_swallows_probe_failures(tmp_path, opencode_cli):
    ws = _make_ws(tmp_path, 200_000)
    cli = opencode_cli("lemonade/Gemma-4-26B-A4B-it-GGUF")
    with patch.object(OpencodeSkillCLI, "_probe_prompt_per_second",
                      side_effect=OSError("connection refused")):
        # Probe failure must NOT skip the test -- fall through to invoke.
        assert cli.preflight_skip(prompt="", workspace_dir=ws,
                                  timeout_seconds=600) is None


def test_default_backend_preflight_returns_none(tmp_path):
    """Non-opencode backends inherit the no-op default."""
    from skills_testing.cli_backends.base import SkillCLIBackend

    class Dummy(SkillCLIBackend):
        name = "dummy"

        def _default_binary_lookup(self):
            return "/bin/true"

        def build_command(self, prompt, workspace_dir):
            return ["true"]

    d = Dummy("x")
    assert d.preflight_skip(prompt="hi", workspace_dir=tmp_path,
                            timeout_seconds=60) is None


def test_preflight_disabled_by_default(tmp_path, opencode_cli, monkeypatch):
    """Without SKILL_TEST_ENABLE_PREFLIGHT, even a guaranteed-too-slow
    case must return None so the local model runs to completion."""
    monkeypatch.delenv("SKILL_TEST_ENABLE_PREFLIGHT", raising=False)
    ws = _make_ws(tmp_path, 200_000)
    cli = opencode_cli("lemonade/Gemma-4-26B-A4B-it-GGUF")
    with patch.object(OpencodeSkillCLI, "_probe_prompt_per_second",
                      return_value=1.0) as p:
        assert cli.preflight_skip(prompt="", workspace_dir=ws,
                                  timeout_seconds=600) is None
    p.assert_not_called()


def test_preflight_explicit_disable_wins(tmp_path, opencode_cli, monkeypatch):
    """SKILL_TEST_DISABLE_PREFLIGHT=1 short-circuits even when the
    enable env var is also set (defensive override for ad-hoc runs)."""
    monkeypatch.setenv("SKILL_TEST_DISABLE_PREFLIGHT", "1")
    ws = _make_ws(tmp_path, 200_000)
    cli = opencode_cli("lemonade/Gemma-4-26B-A4B-it-GGUF")
    with patch.object(OpencodeSkillCLI, "_probe_prompt_per_second",
                      return_value=1.0) as p:
        assert cli.preflight_skip(prompt="", workspace_dir=ws,
                                  timeout_seconds=600) is None
    p.assert_not_called()


def test_lemonade_dispatch_lock_serializes_concurrent_calls():
    """Two threads asking for the lock for the same base URL must
    serialize; different base URLs must not block each other."""
    import threading
    import time as _t

    from skills_testing.cli_backends.opencode import _lemonade_dispatch_lock

    lock_a1 = _lemonade_dispatch_lock("http://localhost:8000/api/v1")
    lock_a2 = _lemonade_dispatch_lock("http://localhost:8000/api/v1")
    lock_b = _lemonade_dispatch_lock("http://other:9000/api/v1")
    assert lock_a1 is lock_a2  # same URL -> same lock instance
    assert lock_a1 is not lock_b

    # Hold the URL-A lock from the main thread; a worker trying to grab
    # it must wait, while a worker on URL-B sails through.
    assert lock_a1.acquire(timeout=0.1)
    try:
        b_done = threading.Event()
        a_done = threading.Event()

        def grab_b():
            assert lock_b.acquire(timeout=0.5)
            lock_b.release()
            b_done.set()

        def grab_a():
            t0 = _t.time()
            assert lock_a1.acquire(timeout=2.0)
            try:
                grab_a.waited = _t.time() - t0
            finally:
                lock_a1.release()
            a_done.set()

        threading.Thread(target=grab_b, daemon=True).start()
        threading.Thread(target=grab_a, daemon=True).start()

        assert b_done.wait(timeout=0.5), "URL-B worker was wrongly blocked"
        assert not a_done.is_set(), "URL-A worker should still be waiting"

        _t.sleep(0.4)
    finally:
        lock_a1.release()

    assert a_done.wait(timeout=2.0), "URL-A worker never acquired"
    assert grab_a.waited >= 0.3, (
        f"URL-A grab waited only {grab_a.waited:.3f}s; lock not enforced"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
