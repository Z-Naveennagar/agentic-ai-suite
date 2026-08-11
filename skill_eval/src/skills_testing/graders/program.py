"""
``program`` grader -- run an external command as a grader.

Ported from waza's program grader. The command is executed directly (no shell),
with the agent's output piped to its stdin and the workspace directory exposed
via environment variables. Exit code 0 -> pass (score 1.0); any non-zero exit
(or timeout) -> fail (score 0.0). The command's stdout becomes the feedback.

Spec (grading_spec.yaml)::

    - id: pytest_passes
      type: program
      command: ./graders/check.sh        # relative paths resolve against case_dir
      args: ["--strict"]
      timeout: 60                          # seconds (default 30)

The grader script receives:
  * the agent output on **stdin**
  * ``WAZA_WORKSPACE_DIR`` and ``SKILL_TEST_WORKSPACE_DIR`` -- the workspace path
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import Grader, GraderContext, GraderResult, register_grader

_DEFAULT_TIMEOUT_S = 30


class ProgramGrader(Grader):
    grader_type = "program"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        command = spec.get("command")
        if not command:
            raise ValueError("program grader must have a 'command'")
        args = [str(a) for a in (spec.get("args") or [])]
        timeout = spec.get("timeout")
        timeout_s = int(timeout) if timeout and int(timeout) > 0 else _DEFAULT_TIMEOUT_S

        resolved = self._resolve_command(ctx, command)

        env = os.environ.copy()
        env["WAZA_WORKSPACE_DIR"] = str(ctx.workspace_dir)
        env["SKILL_TEST_WORKSPACE_DIR"] = str(ctx.workspace_dir)

        base_details = {
            "command": command,
            "resolved_command": resolved,
            "args": args,
            "timeout": timeout_s,
            "workspace_dir": str(ctx.workspace_dir),
        }

        try:
            cp = subprocess.run(
                [resolved, *args],
                input=ctx.stdout,
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
                    "feedback": f"Program timed out after {timeout_s}s",
                },
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            return GraderResult(
                passed=False, score=0.0,
                details={
                    **base_details,
                    "exit_error": str(exc),
                    "feedback": f"Program could not be executed: {exc}",
                },
            )

        notes = (cp.stdout or "").strip()
        err_output = (cp.stderr or "").strip()

        if cp.returncode != 0:
            feedback = f"Program exited with code {cp.returncode}"
            if err_output:
                feedback = f"{feedback}; stderr: {err_output}"
            return GraderResult(
                passed=False, score=0.0,
                details={
                    **base_details,
                    "exit_code": cp.returncode,
                    "stdout": notes,
                    "stderr": err_output,
                    "feedback": feedback,
                },
            )

        return GraderResult(
            passed=True, score=1.0,
            details={
                **base_details,
                "exit_code": 0,
                "stdout": notes,
                "stderr": err_output,
                "feedback": notes or "Program exited successfully",
            },
        )

    @staticmethod
    def _resolve_command(ctx: GraderContext, command: str) -> str:
        """Resolve a relative command against case_dir when it names a file
        there; otherwise return it unchanged (PATH lookup / absolute path)."""
        p = Path(command)
        if p.is_absolute():
            return command
        # Only treat as a path if it looks like one (contains a separator),
        # so bare executables like "pytest" still go through PATH.
        if ctx.case_dir is not None and (os.sep in command or "/" in command):
            candidate = (ctx.case_dir / command)
            if candidate.exists():
                return str(candidate)
        return command


register_grader(ProgramGrader.grader_type, ProgramGrader())
