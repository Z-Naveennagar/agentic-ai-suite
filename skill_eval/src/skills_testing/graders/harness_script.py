"""
``harness_script`` grader -- run a harness-authored script/module as a
grading step and report only whether it ran successfully.

Unlike ``program`` (which pipes the *agent's* output to an external verdict
script and treats its exit code as the case's pass/fail verdict), this
grader runs a script the harness itself owns -- e.g. a live Vivado
block-design read-back -- as one step in the case's ordered grader list.
Its own pass/fail means "did this script execute successfully", nothing
more; it does not interpret any artifact the script produces. A later
grader in the same ``grading_spec.yaml``/``grader_spec.yaml`` list (e.g.
``config_match``) is expected to read whatever the script wrote to the
shared workspace and score it -- that wiring is not part of this grader.

Runs with ``cwd=ctx.workspace_dir``, at grading time -- which is already
after the agent finishes and before the suite's ``reset:``/``teardown:``
lifecycle actions (see ``runner.py``'s call order), so a script needing a
still-live shared Vivado session can use one.

Spec (grader_spec.yaml / grading_spec.yaml)::

    - id: readback
      type: harness_script
      module: skills_testing.runtime.vivado_bd_readback   # run via `-m`
      # script: scripts/my_check.py                        # or a file path,
      #                                                       resolved against
      #                                                       case_dir
      args:
        - --cell={cell_name}        # per-case value, substituted at case-load
                                     # time from test_cases.yaml's `expected:`
                                     # (see case_loader._subst_placeholders)
        - --session-id={session_id} # the group's live Vivado session, filled
                                     # in at GRADE time (see below)
        - --out=outputs/as_built.json
        - --working-dir={workspace} # this case's workspace dir, grade time
      timeout_seconds: 120

``{cell_name}``-style tokens come from the case's own ``expected:`` block
and are already substituted into the spec before this grader ever sees it
(the same mechanism ``config_match``'s ``expected_config: "{expected_config}"``
uses). ``{workspace}`` and ``{session_id}`` cannot be known that early --
the workspace path and the live session id only exist once the case is
actually running -- so this grader substitutes those two tokens itself,
from ``ctx.workspace_dir`` and ``ctx.run_meta["vivado_session_ids"]``
(threaded in by ``runner.py``'s ``_grade``/``_make_ctx``), mirroring how
``core/runner.py:_run_lifecycle_action`` does the same substitution for
suite ``setup:``/``reset:`` actions.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import Grader, GraderContext, GraderResult, register_grader

_DEFAULT_TIMEOUT_S = 120


class HarnessScriptGrader(Grader):
    grader_type = "harness_script"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        module = spec.get("module")
        script = spec.get("script")
        if bool(module) == bool(script):
            raise ValueError(
                "harness_script grader needs exactly one of 'module' or "
                "'script'"
            )
        timeout = spec.get("timeout_seconds")
        timeout_s = (
            int(timeout) if timeout and int(timeout) > 0 else _DEFAULT_TIMEOUT_S
        )

        session_id = (ctx.run_meta.get("vivado_session_ids") or [""])[0]
        args = [
            str(a).replace("{workspace}", str(ctx.workspace_dir))
                  .replace("{session_id}", session_id)
            for a in (spec.get("args") or [])
        ]

        if module:
            cmd = [sys.executable, "-m", module, *args]
            resolved = module
        else:
            resolved = self._resolve_script(ctx, script)
            cmd = [sys.executable, resolved, *args]

        env = os.environ.copy()
        env["SKILL_TEST_WORKSPACE_DIR"] = str(ctx.workspace_dir)

        base_details = {
            "module": module,
            "script": script,
            "resolved": resolved,
            "args": args,
            "timeout_seconds": timeout_s,
            "workspace_dir": str(ctx.workspace_dir),
        }

        try:
            cp = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=env,
                cwd=str(ctx.workspace_dir),
            )
        except subprocess.TimeoutExpired:
            return GraderResult(
                passed=False, score=0.0,
                details={
                    **base_details,
                    "exit_error": f"timed out after {timeout_s}s",
                    "feedback": f"Script timed out after {timeout_s}s",
                },
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            return GraderResult(
                passed=False, score=0.0,
                details={
                    **base_details,
                    "exit_error": str(exc),
                    "feedback": f"Script could not be executed: {exc}",
                },
            )

        stdout = (cp.stdout or "").strip()
        stderr = (cp.stderr or "").strip()

        if cp.returncode != 0:
            feedback = f"Script exited with code {cp.returncode}"
            if stderr:
                feedback = f"{feedback}; stderr: {stderr}"
            return GraderResult(
                passed=False, score=0.0,
                details={
                    **base_details,
                    "exit_code": cp.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "feedback": feedback,
                },
            )

        return GraderResult(
            passed=True, score=1.0,
            details={
                **base_details,
                "exit_code": 0,
                "stdout": stdout,
                "stderr": stderr,
                "feedback": stdout or "Script exited successfully",
            },
        )

    @staticmethod
    def _resolve_script(ctx: GraderContext, script: str) -> str:
        """Resolve a relative ``script:`` path against case_dir, mirroring
        ``program.ProgramGrader._resolve_command``.

        Always returns an absolute path when resolution succeeds: the
        script subprocess runs with ``cwd=ctx.workspace_dir``, not
        whatever directory the case loader happened to run from, so a
        relative ``case_dir`` (or a relative ``candidate`` built from it)
        would resolve against the wrong base at execution time.
        """
        p = Path(script)
        if p.is_absolute():
            return script
        if ctx.case_dir is not None:
            candidate = ctx.case_dir / script
            if candidate.exists():
                return str(candidate.resolve())
        return script


register_grader(HarnessScriptGrader.grader_type, HarnessScriptGrader())
