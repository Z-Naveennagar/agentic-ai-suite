"""
``action_sequence`` grader -- validate tool-call ordering.

Compares the agent's actual tool-call sequence (recovered from the transcript
by :mod:`skills_testing.graders.trace`) against an expected list of actions.
Ported from waza's action_sequence grader, including its three matching modes
and precision/recall/F1 scoring.

The score is the F1 of precision and recall (frequency-aware), so partial
overlaps are graded continuously. ``passed`` reflects the strict matching mode:

    exact_match      identical length, order, and content
    in_order_match   every expected action appears, in order (extras allowed)
    any_order_match  every expected action appears >= as often as required
    presence_match   every expected action appears at least once

``presence_match`` is a presence-only mode: instead of the F1 of
precision/recall, its score is the fraction of *distinct* expected actions
that appear at least once, irrespective of order, repetition, or how many
other (unexpected) tool calls occurred. For ``["A", "B"]`` the score is 1.0
when both appear, 0.5 when only one appears, and ``passed`` is true only when
all appear.

Expected entries may be either a bare tool name (``Read``) or a
command-bearing pattern ``"<tool>: <command>"`` (``"bash: v++ --compile"``).
A command pattern matches a tool call of that tool whose actual executed
command contains the given text (whitespace-normalised, token-subset
tolerant), so the sequence can assert *what was run*, not just that a Bash
tool fired. The actual executed commands are always surfaced in
``details.actual_commands`` regardless of the expected shape.

Spec (grading_spec.yaml)::

    - id: dataflow_pipeline
      type: action_sequence
      matching_mode: in_order_match     # exact_match | in_order_match | any_order_match | presence_match
      expected_actions:                 # `tool_sequence` accepted as an alias
        - Read
        - Skill
        - "bash: v++ --compile --mode hls"
"""

from __future__ import annotations

from collections import Counter

from . import Grader, GraderContext, GraderResult, register_grader
from .trace import (
    canonical_mcp_name,
    command_matches,
    tool_calls_detailed,
    tool_commands,
    tool_names,
)

_MODES = {"exact_match", "in_order_match", "any_order_match", "presence_match"}


def _canonical_entry(entry: str, aliases) -> str:
    """Canonicalize the tool identity of an expected entry, server-agnostic.

    A bare name (``mcp__vivado-doc-search__vivado_doc_search``) is reduced
    whole; a ``<tool>: <command>`` pattern has only its tool half reduced so
    the command text is preserved verbatim.
    """
    if _is_command_entry(entry):
        tool, cmd = entry.split(":", 1)
        return f"{canonical_mcp_name(tool.strip(), aliases)}:{cmd}"
    return canonical_mcp_name(entry, aliases)


class ActionSequenceGrader(Grader):
    grader_type = "action_sequence"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        # `tool_sequence` is the suite-format alias for `expected_actions`
        # (the token a grader_spec `grader_args: '{tool_sequence}'` resolves to).
        raw = spec.get("expected_actions")
        if raw is None:
            raw = spec.get("tool_sequence")
        # A bare string here (e.g. a raw, unresolved "{tool_sequence}"
        # placeholder that slipped past case_loader.py's own guard, or an
        # author typing `tool_sequence: Read` without brackets) must not
        # reach `list(...)` below -- Python explodes a string into its
        # individual characters rather than treating it as a one-item list,
        # silently producing a nonsense multi-entry "expected_actions" that
        # always fails instead of a clear error.
        if isinstance(raw, str):
            raise ValueError(
                "action_sequence grader: 'expected_actions'/'tool_sequence' "
                f"must be a list, got a bare string {raw!r} -- wrap it in "
                "brackets (e.g. [Read]) if a single tool was intended"
            )
        raw = list(raw or [])
        if not raw:
            raise ValueError(
                "action_sequence grader must have at least one "
                "'expected_actions' entry"
            )
        # An entry may be a bare string, or (presence_match only) a *list* of
        # alternatives -- an any-of group that is satisfied when ANY alternative
        # matches (e.g. "the design was executed via the MCP tool OR a
        # `vivado -mode batch` Bash call"). Preserve the raw shape for details.
        expected = [
            [str(a) for a in e] if isinstance(e, (list, tuple)) else str(e)
            for e in raw
        ]

        mode = str(spec.get("matching_mode", "in_order_match")).strip().lower()
        if mode not in _MODES:
            raise ValueError(
                f"action_sequence grader: invalid matching_mode {mode!r} "
                "(must be exact_match, in_order_match, any_order_match, or "
                "presence_match)"
            )
        if mode != "presence_match" and any(
            isinstance(e, list) for e in expected
        ):
            raise ValueError(
                "action_sequence grader: any-of alternatives (list entries) "
                "are only supported in presence_match mode"
            )

        client = ctx.run_meta.get("client")
        # MCP tool identity is matched server-agnostically: the same logical
        # tool can be reached through different MCP servers (and named
        # differently per backend), so both the expected entries and the
        # actual calls are reduced to their ``mcp__<family>__<tool>`` identity
        # before comparison. Raw names are still surfaced in the details for
        # debuggability; ``canonical_*`` shows exactly what was compared.
        aliases = ctx.run_meta.get("mcp_server_aliases")
        actual = tool_names(ctx.stdout, ctx.stderr, client=client)
        actual_commands = tool_commands(ctx.stdout, ctx.stderr, client=client)

        # Canonicalize each entry, preserving any-of groups as lists.
        expected_canon = [
            [_canonical_entry(a, aliases) for a in e]
            if isinstance(e, list) else _canonical_entry(e, aliases)
            for e in expected
        ]
        actual_canon = [canonical_mcp_name(a, aliases) for a in actual]

        # When any expected entry (or any alternative within an any-of group)
        # carries a command (``<tool>: <cmd>``) we match against the
        # command-annotated call list; otherwise we keep the original name-only
        # Counter/order semantics unchanged.
        has_commands = any(
            any(_is_command_entry(a) for a in e) if isinstance(e, list)
            else _is_command_entry(e)
            for e in expected_canon
        )
        pairs_canon = None
        if has_commands:
            pairs = tool_calls_detailed(ctx.stdout, ctx.stderr, client=client)
            pairs_canon = [
                (canonical_mcp_name(n, aliases), c) for n, c in pairs
            ]

        if mode == "presence_match":
            # Presence-only: score is the fraction of distinct expected entries
            # (any-of groups count as one) that appear at least once,
            # irrespective of order, repetition, or how many other (unexpected)
            # tool calls occurred.
            passed, score, precision, recall = _match_presence(
                expected_canon, actual_canon, pairs_canon
            )
            f1 = score
        elif has_commands:
            passed, precision, recall = _match_with_commands(
                mode, expected_canon, pairs_canon
            )
            f1 = _f1(precision, recall)
            score = f1
        else:
            precision, recall = _precision_recall(expected_canon, actual_canon)
            passed = _check_match(mode, expected_canon, actual_canon)
            f1 = _f1(precision, recall)
            score = f1

        feedback = (
            "Action sequence matched"
            if passed
            else _failure_feedback(mode, expected_canon, actual_canon)
        )

        return GraderResult(
            passed=passed,
            score=score,
            details={
                "matching_mode": mode,
                "expected_actions": expected,
                "actual_actions": actual,
                "canonical_expected": expected_canon,
                "canonical_actions": actual_canon,
                "actual_commands": actual_commands,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "feedback": feedback,
            },
        )


# -- command-aware matching --------------------------------------------------


def _is_command_entry(entry: str) -> bool:
    """True when *entry* is a ``<tool>: <command>`` pattern, not a bare name."""
    return isinstance(entry, str) and ":" in entry


def _entry_matches(entry: str, name: str, command: str) -> bool:
    if _is_command_entry(entry):
        want_tool, want_cmd = entry.split(":", 1)
        want_tool = want_tool.strip().lower()
        if want_tool and name.lower() != want_tool:
            return False
        return command_matches(command, want_cmd)
    return name == entry


def _match_with_commands(
    mode: str, expected: list[str], pairs: list[tuple[str, str]],
) -> tuple[bool, float, float]:
    """Match command-bearing expected entries against ``(name, command)`` calls.

    Returns ``(passed, precision, recall)``. ``in_order_match`` /
    ``exact_match`` consume calls left-to-right; ``any_order_match`` only
    requires each expected entry to match somewhere.
    """
    def _find(entry: str, start: int) -> int:
        for i in range(start, len(pairs)):
            if _entry_matches(entry, pairs[i][0], pairs[i][1]):
                return i
        return -1

    if mode == "any_order_match":
        passed = all(_find(e, 0) >= 0 for e in expected)
    else:  # in_order_match / exact_match both consume in order
        idx = 0
        passed = True
        for e in expected:
            j = _find(e, idx)
            if j < 0:
                passed = False
                break
            idx = j + 1
        if mode == "exact_match":
            passed = passed and len(pairs) == len(expected)

    matched = sum(1 for e in expected if _find(e, 0) >= 0)
    recall = matched / len(expected) if expected else 1.0
    precision = matched / len(pairs) if pairs else 0.0
    return passed, precision, recall


def _match_presence(
    expected: "list[str | list[str]]",
    actual: list[str],
    pairs: "list[tuple[str, str]] | None" = None,
) -> tuple[bool, float, float, float]:
    """Presence-only match, with any-of group support.

    Scores the fraction of *distinct* expected entries that appear at least
    once in the actual calls, ignoring order, repetition, and any additional
    (unexpected) tool calls. An entry may be an any-of group (a list of
    alternatives); the group counts as present when ANY alternative matches.
    ``passed`` is true only when every expected entry is present. Returns
    ``(passed, score, precision, recall)``; precision and recall are reported
    equal to the presence fraction, since extra calls are deliberately not
    penalised.

    When *pairs* (``(name, command)`` calls) is given, entries are matched
    against it (``_entry_matches`` handles both name-only and command entries);
    otherwise name-only entries are matched against *actual*.
    """
    # Normalize to groups (a bare entry is a single-alternative group) and
    # dedupe order-preservingly via tuple keys (lists are unhashable).
    groups: list[list[str]] = [
        list(e) if isinstance(e, list) else [e] for e in expected
    ]
    distinct: list[list[str]] = []
    seen: set = set()
    for g in groups:
        key = tuple(g)
        if key in seen:
            continue
        seen.add(key)
        distinct.append(g)
    if not distinct:
        return True, 1.0, 1.0, 1.0

    actual_set = set(actual)

    def _group_present(group: list[str]) -> bool:
        for alt in group:
            if pairs is not None:
                if any(_entry_matches(alt, n, c) for n, c in pairs):
                    return True
            elif alt in actual_set:
                return True
        return False

    present = sum(1 for g in distinct if _group_present(g))
    score = present / len(distinct)
    passed = present == len(distinct)
    return passed, score, score, score


# -- matching ----------------------------------------------------------------


def _check_match(mode: str, expected: list[str], actual: list[str]) -> bool:
    if mode == "exact_match":
        return actual == expected
    if mode == "in_order_match":
        return _in_order(expected, actual)
    return _any_order(expected, actual)


def _in_order(expected: list[str], actual: list[str]) -> bool:
    idx = 0
    for a in actual:
        if idx < len(expected) and a == expected[idx]:
            idx += 1
    return idx == len(expected)


def _any_order(expected: list[str], actual: list[str]) -> bool:
    exp = Counter(expected)
    act = Counter(actual)
    return all(act[action] >= needed for action, needed in exp.items())


# -- scoring -----------------------------------------------------------------


def _precision_recall(expected: list[str], actual: list[str]):
    if not expected and not actual:
        return 1.0, 1.0

    exp = Counter(expected)
    act = Counter(actual)
    # True positives: min(expected, actual) per expected action.
    tp = sum(min(needed, act[action]) for action, needed in exp.items())

    precision = tp / len(actual) if actual else 0.0
    recall = tp / len(expected) if expected else 0.0
    return precision, recall


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _failure_feedback(mode: str, expected: list[str], actual: list[str]) -> str:
    if mode == "exact_match":
        return (
            f"Exact match failed: expected {len(expected)} actions {expected}, "
            f"got {len(actual)} actions {actual}"
        )
    if mode == "in_order_match":
        return (
            f"In-order match failed: not all expected actions {expected} "
            f"appeared in order within actual {actual}"
        )
    if mode == "presence_match":
        return (
            f"Presence match failed: not all expected actions {expected} "
            f"appeared at least once in actual {actual}"
        )
    exp = Counter(expected)
    act = Counter(actual)
    missing = [
        f"{action} (need {needed}, got {act[action]})"
        for action, needed in exp.items()
        if act[action] < needed
    ]
    return (
        "Any-order match failed: missing or insufficient actions: "
        + ", ".join(missing)
    )


register_grader(ActionSequenceGrader.grader_type, ActionSequenceGrader())
