"""
Per-CLI environment overrides used by the without-skill A/B arm to hide
agent skills from a CLI's discovery path.

Scope guarantees
----------------
These recipes ONLY affect skill discovery.  They do NOT disable MCP
servers, bash/file tools, or any other CLI capability.  MCP wiring for
each client is governed by the per-workspace config file (e.g.
``opencode.json``) which the CLI backend writes with
``mcp.<server>.enabled: true`` in both arms.

Provenance per client
---------------------
``opencode``:
    Env vars verified by enumerating the shipped binary
    (``strings $(which opencode) | grep OPENCODE_``).  Confirmed to
    affect only skill discovery:
      - OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1
          Disables the built-in Claude Code skills discovery walk
          (``.claude/skills/`` in CWD and ``~/.claude/skills/``).
      - OPENCODE_DISABLE_EXTERNAL_SKILLS=1
          Disables external / plugin-provided skill sources.
    Note: earlier versions of this file set ``OPENCODE_SKILLS_DIR``
    and ``AGENT_SKILLS_DIR``.  Those env vars do not exist in opencode
    and were silent no-ops, which meant the "no-skill" arm could still
    discover ``~/.claude/skills/``.  Fixed 2026-04.

Other clients (``claude_code``, ``cursor``, ``copilot``, ``goose``,
``qwen``) use best-effort env vars that match each client's documented
knobs where available.  Discovery for those CLIs also relies on the
workspace ``.claude/skills/`` tree being absent in the no-skill arm
(the runner never stages it when ``with_skill=False``), so even if an
env var is a no-op, a well-behaved CWD-first client is still skill-free
for that run.
"""

from __future__ import annotations

# Each recipe: env vars to set when hiding skills for this CLI.
# Values are strings; meaning is "skills off" (for flags that's "1").
_RECIPES: dict[str, dict[str, str]] = {
    "opencode": {
        # Real, verified opencode env vars (see module docstring for how
        # these were identified).  Only skill discovery is affected; MCP,
        # bash, file tools, etc. remain fully available.
        "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
        "OPENCODE_DISABLE_EXTERNAL_SKILLS":    "1",
    },
    # Claude Code's open Skills 2.0 discovery exposes a configurable set
    # of skill roots via env.  ``/dev/null`` makes nothing discoverable.
    "claude_code": {
        "CLAUDE_SKILLS_DIR":  "/dev/null",
        "AGENT_SKILLS_DIR":   "/dev/null",
        "ANTHROPIC_SKILLS":   "/dev/null",
    },
    "cursor": {
        "CURSOR_SKILLS_DIR":  "/dev/null",
        "AGENT_SKILLS_DIR":   "/dev/null",
    },
    "copilot": {
        "GITHUB_COPILOT_SKILLS_DIR": "/dev/null",
        "AGENT_SKILLS_DIR":          "/dev/null",
    },
    "goose": {
        "GOOSE_SKILLS_DIR":    "/dev/null",
        "AGENT_SKILLS_DIR":    "/dev/null",
    },
    "qwen": {
        "QWEN_SKILLS_DIR":     "/dev/null",
        "AGENT_SKILLS_DIR":    "/dev/null",
    },
}


# Env vars that are intentionally *not* set by this module because they
# disable capabilities the harness wants to preserve (e.g. MCP, project
# config file, Claude Code prompt).  Kept here as a trip-wire: anything
# added to ``_RECIPES`` below must NOT be in this set.
_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "OPENCODE_DISABLE_DEFAULT_PLUGINS",    # would kill bundled tools
    "OPENCODE_DISABLE_CLAUDE_CODE",        # sledgehammer; takes out prompt too
    "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT", # harms answer quality
    "OPENCODE_DISABLE_PROJECT_CONFIG",     # would disable opencode.json → MCP
})


def hide_skills_env(client: str) -> dict[str, str]:
    """Return env-var overrides to suppress skill discovery for *client*.

    Returns {} for unknown clients so the caller can decide whether to
    skip the without-skill arm or treat the missing recipe as a no-op.
    """
    recipe = dict(_RECIPES.get(client, {}))
    bad = set(recipe) & _FORBIDDEN_KEYS
    if bad:  # pragma: no cover - defensive, not expected in practice
        raise RuntimeError(
            f"skill_hider recipe for {client!r} contains forbidden "
            f"capability-disabling env vars: {sorted(bad)}"
        )
    return recipe


def redirect_skills_env(client: str, skills_dir) -> dict[str, str]:
    """Return env-var overrides that point *client*'s skill-discovery
    path at *skills_dir* instead of the user's home tree.

    Historically used to force clients to look at the per-test workspace's
    ``.claude/skills/`` rather than ``~/.claude/skills/``.  With the
    2026-04 opencode fix this is only still useful for clients whose
    published env vars accept a filesystem path (claude_code, cursor,
    copilot, goose, qwen).  For opencode — which exposes *disable*
    flags, not a path — this returns {} and the caller should rely on
    CWD-based discovery of the workspace ``.claude/skills/`` instead.
    """
    if client == "opencode":
        # opencode has no SKILLS_DIR knob; its discovery walks CWD and
        # ~/.claude/skills/.  The runner stages the workspace tree, so
        # no env-level redirect is needed.  Returning {} keeps the
        # with-skill arm honest: don't pretend to redirect a knob the
        # CLI doesn't expose.
        return {}
    target = str(skills_dir)
    return {k: target for k in _RECIPES.get(client, {})}
