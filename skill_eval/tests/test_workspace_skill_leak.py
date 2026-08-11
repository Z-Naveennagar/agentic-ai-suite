"""
Regression tests for the A/B skill-leak fix in
``skills_testing/workspace.py``.

The bug being guarded against: a manifest's ``external_inputs`` block
that targets ``.claude/skills/<name>/`` (or ``.cursor/rules/``,
``.cursor/skills/``, ``AGENTS.md``) was being staged into the workspace
for BOTH arms, including the no-skill arm. Since CLIs CWD-walk for
these skill directories, the no-skill arm would silently re-acquire the
skill via the filesystem even with the env-var hider in effect. The two
arms then produced identical artifacts and graders couldn't distinguish
them.

The fix: ``Workspace`` learns an ``allow_skill_inputs`` flag. When
False, ``populate()`` drops any external_input whose ``dest`` lands
inside any skill-discovery path and records the skipped paths so the
runner can log them.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from skills_testing.runtime.workspace import Workspace, create_workspace


def _make_skill_tree(root: Path, skill_name: str) -> Path:
    sk = root / ".claude" / "skills" / skill_name
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text(
        "---\nname: {n}\ndescription: test\n---\n# body\n".format(n=skill_name)
    )
    (sk / "reference").mkdir()
    (sk / "reference" / "step.md").write_text("step contents\n")
    return sk


@pytest.fixture
def staged_skill_src(tmp_path: Path) -> Path:
    """A pretend on-disk source skill tree the manifest would point to
    via ``external_inputs.src``. Lives outside the workspace dir."""
    src_root = tmp_path / "external"
    return _make_skill_tree(src_root, "demo-skill")


def test_no_skill_arm_drops_external_skill_inputs(staged_skill_src, tmp_path):
    extra_src = tmp_path / "external" / "extra.md"
    extra_src.write_text("not a skill\n")

    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(staged_skill_src),
             "dest": ".claude/skills/demo-skill"},
            # Non-skill external input must still be staged.
            {"src": str(extra_src),
             "dest": "inputs/extra.md"},
        ],
        allow_skill_inputs=False,
    )

    ws.populate()

    # Skill tree was filtered out.
    assert not (ws.dir / ".claude" / "skills").exists(), \
        ".claude/skills/ must NOT be staged in the no-skill arm"
    # Non-skill external input survived.
    assert (ws.dir / "inputs" / "extra.md").is_file()
    # Skipped paths surfaced for runner-side logging.
    assert ws._skipped_skill_inputs == [".claude/skills/demo-skill"]


def test_skill_arm_still_stages_external_skill_inputs(staged_skill_src, tmp_path):
    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(staged_skill_src),
             "dest": ".claude/skills/demo-skill"},
        ],
        allow_skill_inputs=True,  # default for SKILL arm
    )
    ws.populate()

    sk = ws.dir / ".claude" / "skills" / "demo-skill"
    assert sk.is_dir()
    assert (sk / "SKILL.md").is_file()
    assert (sk / "reference" / "step.md").is_file()
    assert ws._skipped_skill_inputs == []


def test_filter_handles_nested_skill_dest_paths(staged_skill_src, tmp_path):
    """Some manifests target a sub-skill directly, e.g.
    ``.claude/skills/rtl-assistant/rtl-lint``. The filter must catch
    both the top-level and the nested form."""
    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(staged_skill_src),
             "dest": ".claude/skills/parent/sub-skill"},
        ],
        allow_skill_inputs=False,
    )
    ws.populate()
    assert not (ws.dir / ".claude" / "skills").exists()
    assert ws._skipped_skill_inputs == [".claude/skills/parent/sub-skill"]


def test_filter_does_not_match_unrelated_paths(tmp_path):
    """Defensive: a path that merely *contains* the substring ``skills``
    but is NOT under ``.claude/skills/`` should still be staged."""
    src_root = tmp_path / "external"
    src_root.mkdir()
    src_file = src_root / "skills_overview.txt"
    src_file.write_text("not actually a skill\n")
    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(src_file), "dest": "docs/skills_overview.txt"},
        ],
        allow_skill_inputs=False,
    )
    ws.populate()
    assert (ws.dir / "docs" / "skills_overview.txt").is_file()
    assert ws._skipped_skill_inputs == []


def test_cursor_rules_filtered_in_no_skill_arm(tmp_path):
    """Cursor Agent discovers rules from .cursor/rules/. The no-skill
    arm must filter external_inputs targeting that path."""
    src_root = tmp_path / "external"
    src_root.mkdir()
    rule_file = src_root / "rtl-lint.mdc"
    rule_file.write_text("# RTL lint rule\n")

    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(rule_file), "dest": ".cursor/rules/rtl-lint.mdc"},
        ],
        allow_skill_inputs=False,
    )
    ws.populate()
    assert not (ws.dir / ".cursor" / "rules").exists()
    assert ".cursor/rules/rtl-lint.mdc" in ws._skipped_skill_inputs


def test_cursor_skills_filtered_in_no_skill_arm(tmp_path):
    """Cursor can also discover skills from .cursor/skills/."""
    src_root = tmp_path / "external"
    src_root.mkdir()
    skill_file = src_root / "SKILL.md"
    skill_file.write_text("# A cursor skill\n")

    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(skill_file), "dest": ".cursor/skills/my-skill/SKILL.md"},
        ],
        allow_skill_inputs=False,
    )
    ws.populate()
    assert not (ws.dir / ".cursor" / "skills").exists()
    assert ".cursor/skills/my-skill/SKILL.md" in ws._skipped_skill_inputs


def test_agents_md_filtered_in_no_skill_arm(tmp_path):
    """AGENTS.md at the workspace root provides agent instructions.
    Must be blocked in the no-skill arm."""
    src_root = tmp_path / "external"
    src_root.mkdir()
    agents = src_root / "AGENTS.md"
    agents.write_text("# Agent instructions\n")

    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(agents), "dest": "AGENTS.md"},
        ],
        allow_skill_inputs=False,
    )
    ws.populate()
    assert not (ws.dir / "AGENTS.md").exists()
    assert "AGENTS.md" in ws._skipped_skill_inputs


def test_cursor_paths_allowed_in_skill_arm(tmp_path):
    """The skill arm must still stage .cursor/ and AGENTS.md inputs."""
    src_root = tmp_path / "external"
    src_root.mkdir()
    (src_root / "rule.mdc").write_text("rule\n")
    (src_root / "AGENTS.md").write_text("instructions\n")

    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(src_root / "rule.mdc"),
             "dest": ".cursor/rules/lint.mdc"},
            {"src": str(src_root / "AGENTS.md"), "dest": "AGENTS.md"},
        ],
        allow_skill_inputs=True,
    )
    ws.populate()
    assert (ws.dir / ".cursor" / "rules" / "lint.mdc").is_file()
    assert (ws.dir / "AGENTS.md").is_file()
    assert ws._skipped_skill_inputs == []


def test_default_allow_skill_inputs_preserves_legacy_behaviour(staged_skill_src, tmp_path):
    """Callers that don't pass the new flag (e.g. the unit-test fixture
    in test_runner.py) must still stage external skill inputs, so we
    don't break tests that rely on the old behaviour."""
    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(staged_skill_src),
             "dest": ".claude/skills/demo-skill"},
        ],
        # allow_skill_inputs not specified -> defaults to True
    )
    ws.populate()
    assert (ws.dir / ".claude" / "skills" / "demo-skill" / "SKILL.md").is_file()


def test_opencode_skills_filtered_in_no_skill_arm(tmp_path):
    """opencode discovers project skills from .opencode/skills/. The
    no-skill arm must filter external_inputs targeting that path, exactly
    like it does for .claude/skills/."""
    src_root = tmp_path / "external"
    src_root.mkdir()
    skill_file = src_root / "SKILL.md"
    skill_file.write_text("# An opencode skill\n")

    ws_root = tmp_path / "ws"
    ws = create_workspace(
        case_id="demo",
        root=ws_root,
        external_inputs=[
            {"src": str(skill_file), "dest": ".opencode/skills/my-skill/SKILL.md"},
        ],
        allow_skill_inputs=False,
    )
    ws.populate()
    assert not (ws.dir / ".opencode" / "skills").exists()
    assert ".opencode/skills/my-skill/SKILL.md" in ws._skipped_skill_inputs


# ---- per-client skills_dest staging ------------------------------------


def _make_src_skill_tree(tmp_path: Path) -> Path:
    """A source skill root (as ``skills_root`` would point to) holding one
    skill body. Distinct from the external_inputs fixture above."""
    src = tmp_path / "src_skills"
    (src / "demo").mkdir(parents=True)
    (src / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: test\n---\n# body\n"
    )
    return src


def test_skills_dest_defaults_to_claude(tmp_path):
    """Callers that don't set skills_dest stage into .claude/skills, the
    historical location (Claude Code / Copilot)."""
    src = _make_src_skill_tree(tmp_path)
    ws = create_workspace(
        case_id="demo", root=tmp_path / "ws", skills_root=src,
        # skills_dest not specified -> defaults to .claude/skills
    )
    ws.populate()
    assert (ws.dir / ".claude" / "skills" / "demo" / "SKILL.md").is_file()
    assert not (ws.dir / ".opencode").exists()


def test_skills_dest_opencode_stages_under_opencode_only(tmp_path):
    """With skills_dest='.opencode/skills' the tree lands under
    .opencode/skills and NOT under .claude/skills -- so opencode's own
    project-skill discovery sees the workspace copy and no stray
    .claude/skills tree is left behind."""
    src = _make_src_skill_tree(tmp_path)
    ws = create_workspace(
        case_id="demo", root=tmp_path / "ws", skills_root=src,
        skills_dest=".opencode/skills",
    )
    ws.populate()
    assert (ws.dir / ".opencode" / "skills" / "demo" / "SKILL.md").is_file()
    assert not (ws.dir / ".claude" / "skills").exists()


def test_skills_dir_for_maps_clients():
    """The runner picks skills_dest from the backend class attribute:
    opencode -> .opencode/skills, everyone else -> .claude/skills."""
    from skills_testing.cli_backends import skills_dir_for
    assert skills_dir_for("opencode") == ".opencode/skills"
    assert skills_dir_for("claude_code") == ".claude/skills"
    assert skills_dir_for("cursor") == ".claude/skills"
    assert skills_dir_for("copilot") == ".claude/skills"
    # Unknown client falls back to the historical default.
    assert skills_dir_for("does-not-exist") == ".claude/skills"


# ---- per-client skills SOURCE root -------------------------------------


def _runner_with_skills_root(root):
    """A SkillRunner instance with only ``skills_root`` set, enough to
    exercise ``_skills_root_for`` without a full construction."""
    from skills_testing.core.runner import SkillRunner
    r = SkillRunner.__new__(SkillRunner)
    r.skills_root = Path(root).resolve() if root else None
    return r


def test_skills_root_for_opencode_uses_sibling_opencode_source(tmp_path):
    """opencode links the sibling ``.opencode/skills`` source, not the
    configured ``.claude/skills`` -- so the workspace symlink target (and
    any cache the skill writes back) stays under ``.opencode``."""
    base = tmp_path / "repo"
    (base / ".claude" / "skills").mkdir(parents=True)
    (base / ".opencode" / "skills").mkdir(parents=True)
    r = _runner_with_skills_root(base / ".claude" / "skills")

    assert r._skills_root_for("opencode") == (base / ".opencode" / "skills").resolve()
    # Other clients keep the configured .claude/skills source.
    assert r._skills_root_for("claude_code") == (base / ".claude" / "skills").resolve()


def test_skills_root_for_opencode_falls_back_when_no_sibling(tmp_path):
    """If no ``.opencode/skills`` source exists, opencode falls back to the
    configured root rather than staging nothing."""
    base = tmp_path / "repo"
    (base / ".claude" / "skills").mkdir(parents=True)
    r = _runner_with_skills_root(base / ".claude" / "skills")
    assert r._skills_root_for("opencode") == (base / ".claude" / "skills").resolve()


def test_skills_root_for_custom_layout_is_honored_as_is(tmp_path):
    """A custom skills_root not ending in .claude/skills is used verbatim
    for every client (we can't infer a sibling for an unknown layout)."""
    custom = tmp_path / "my_skills"
    custom.mkdir()
    r = _runner_with_skills_root(custom)
    assert r._skills_root_for("opencode") == custom.resolve()
    assert r._skills_root_for("claude_code") == custom.resolve()


def test_skills_root_for_none_stays_none():
    r = _runner_with_skills_root(None)
    assert r._skills_root_for("opencode") is None
