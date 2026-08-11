"""
``config_match`` grader -- tolerant comparison of a recorded "as-configured"
artifact against a known-value expected-config map.

Ported from the standalone ``ip-configurator`` blind benchmark's
``grade_blind_run.py`` (see
``hls-llm-skills-main/test/ip-configurator-test-kit/workspace/scripts/``).
That script compared IP block-design CONFIG.* read-backs against an answer
key with several intentional tolerances (numeric fuzz, true/false<->1/0,
comma-list element-wise compare, nested-dict <-> flat key canonicalization,
port-name keys ignored, empty-expected = creation-only). This grader
provides the same comparison as a first-class harness grader type.

Expected-config source (in priority order)
--------------------------------------------
1. ``expected_config`` inline in the spec -- a dict. In practice this is
   written in grader_spec.yaml as the literal string ``"{expected_config}"``;
   ``case_loader.py``'s per-case template substitution replaces that exact
   ``{key}`` token with the real dict from that case's ``test_cases.yaml``
   ``expected:`` block (whole-value passthrough, not string interpolation),
   so ``expected_config`` never needs to be duplicated into a separate file.
2. ``expected_config_file`` -- a fallback path, resolved relative to
   ``ctx.case_dir`` (so it can point at a JSON file staged under the suite's
   ``inputs/`` directory, or anywhere else under the case directory), used
   only when ``expected_config`` above is absent.

Actual-config source
---------------------
``artifact`` -- a path resolved relative to ``ctx.workspace_dir``: the file
the agent itself produced during the run. Accepts either a single JSON
object (optionally wrapping the map under an ``as_configured`` key) or a
JSONL file (the last line is used).

Spec (grader_spec.yaml)::

    - id: config_match
      type: config_match
      expected_config: "{expected_config}"     # inline, from test_cases.yaml
      # expected_config_file: inputs/expected_config.json   # fallback
      artifact: outputs/as_configured.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import Grader, GraderContext, GraderResult, register_grader

# Absolute + relative numeric tolerance for value comparison.
ABS_TOL = 0.05
REL_TOL = 0.001


def _norm_scalar(v: Any) -> str:
    """Lower/trim, map true/false<->1/0, collapse whitespace and trailing zeros."""
    s = str(v).strip().lower()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    s = re.sub(r"\s+", " ", s)
    if s == "true":
        return "1"
    if s == "false":
        return "0"
    if re.fullmatch(r"[0-9]+\.[0-9]+", s):
        s = s.rstrip("0").rstrip(".")
    return s


def _as_float(s: str):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _scalar_equal(exp: str, got: str) -> bool:
    ne, ng = _norm_scalar(exp), _norm_scalar(got)
    if ne == ng:
        return True
    fe, fg = _as_float(ne), _as_float(ng)
    if fe is not None and fg is not None:
        return abs(fe - fg) <= max(ABS_TOL, REL_TOL * max(abs(fe), abs(fg)))
    return False


def _is_port_name_key(key: str) -> bool:
    """Port-name params are ignored (the chosen port names don't matter)."""
    k = key.upper()
    return k.endswith("_PORT") or k == "CONFIG.CLKOUT_PORT"


def _canon_key(key: str) -> str:
    """Canonicalize a CONFIG key so nested-dict and flat notations compare equal.

    ``CONFIG.PS11_CONFIG(FOO)`` and the flat ``CONFIG.FOO`` both canonicalize
    to the inner key ``FOO``.
    """
    s = str(key)
    if s.upper().startswith("CONFIG."):
        s = s[len("CONFIG."):]
    m = re.fullmatch(r"[A-Za-z0-9_]+\((.+)\)", s)
    if m:
        s = m.group(1)
    elif "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.upper()


def _compare_value(exp: Any, got: Any) -> bool:
    """Compare one expected value against the as-configured value (with tolerances)."""
    if got is None:
        return False
    exp_s, got_s = str(exp), str(got)
    # Comma-list params: compare element-wise so per-element precision
    # differences still pass.
    if "," in exp_s or "," in got_s:
        ep = exp_s.split(",")
        gp = got_s.split(",")
        if len(ep) != len(gp):
            return False
        return all(_scalar_equal(a, b) for a, b in zip(ep, gp))
    return _scalar_equal(exp_s, got_s)


def _flatten_configured(configured: dict) -> dict:
    """Expand nested-dict CONFIG values into the dotted-paren notation.

    e.g. ``{"CONFIG.PS11_CONFIG": {"FOO": "1"}}`` -> ``{"CONFIG.PS11_CONFIG(FOO)": "1"}``
    so it compares against the answer key's nested-key notation (and, via
    ``_canon_key``, the flat form too).
    """
    out: dict = {}
    for k, v in configured.items():
        if isinstance(v, dict):
            outer = k[len("CONFIG."):] if str(k).upper().startswith("CONFIG.") else str(k)
            for sub, sv in v.items():
                out[f"CONFIG.{outer}({sub})"] = sv
        else:
            out[k] = v
    return out


def _is_disabled_peripheral(exp: Any) -> bool:
    """An expected ``ENABLE 0 ...`` value matches a missing as-configured value
    (leaving a peripheral at its absent default is functionally identical)."""
    return isinstance(exp, str) and exp.strip().upper().startswith("ENABLE 0")


def _grade_one(expected: dict, configured: dict) -> dict:
    """Grade one case's expected_config against its recorded as_configured dict."""
    if not expected:
        return {"status": "CREATION_ONLY", "passed": True, "matched": 0, "total": 0,
                "ignored": [], "mismatches": []}

    configured = _flatten_configured(configured)
    configured_canon = {_canon_key(k): v for k, v in configured.items()}

    matched, ignored, mismatches, required = 0, [], [], 0
    for key, exp in expected.items():
        if _is_port_name_key(key):
            ignored.append(key)
            continue
        required += 1
        got = configured.get(key)
        if got is None:
            got = configured_canon.get(_canon_key(key))
        if _compare_value(exp, got) or (got is None and _is_disabled_peripheral(exp)):
            matched += 1
        else:
            mismatches.append({"key": key, "expected": exp,
                                "got": got if got is not None else "<missing>"})

    passed = matched == required
    return {"status": "PASS" if passed else "FAIL", "passed": passed,
            "matched": matched, "total": required, "ignored": ignored,
            "mismatches": mismatches}


def _load_actual_config(path: Path) -> dict:
    """Read the agent-produced artifact: a single JSON object, optionally
    wrapping the map under an ``as_configured`` key, or a JSONL file (last
    valid line used)."""
    if not path.exists():
        return {}
    text = path.read_text().strip()
    if not text:
        return {}
    try:
        rec = json.loads(text)
    except json.JSONDecodeError:
        rec = None
        for ln in reversed(text.splitlines()):
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
                break
            except json.JSONDecodeError:
                continue
    if isinstance(rec, dict):
        inner = rec.get("as_configured")
        return inner if isinstance(inner, dict) else rec
    return {}


class ConfigMatchGrader(Grader):
    grader_type = "config_match"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        expected = spec.get("expected_config")
        if expected is None:
            cfg_file = spec.get("expected_config_file")
            if cfg_file:
                base = ctx.case_dir or ctx.workspace_dir
                cfg_path = base / cfg_file
                if cfg_path.exists():
                    expected = json.loads(cfg_path.read_text())
        expected = expected or {}
        if not isinstance(expected, dict):
            raise ValueError(
                "config_match grader: 'expected_config' must resolve to a mapping"
            )

        artifact_rel = spec.get("artifact")
        if not artifact_rel:
            raise ValueError("config_match grader requires 'artifact'")
        configured = _load_actual_config(ctx.workspace_dir / artifact_rel)

        result = _grade_one(expected, configured)
        total = result["total"]
        score = (result["matched"] / total) if total else 1.0

        feedback = (
            "Creation-only (no CONFIG.* keys expected)"
            if result["status"] == "CREATION_ONLY"
            else f"{result['matched']}/{result['total']} CONFIG keys matched"
        )
        if result["mismatches"]:
            feedback += ": " + "; ".join(
                f"{m['key']} want {m['expected']!r} got {m['got']!r}"
                for m in result["mismatches"][:5]
            )

        return GraderResult(
            passed=result["passed"],
            score=score,
            details={**result, "feedback": feedback},
        )


register_grader(ConfigMatchGrader.grader_type, ConfigMatchGrader())
