"""
``discovery_first`` grader -- did the agent LOOK before it WROTE?

Procedural correctness, not outcome correctness. A case can build the right
design by a path that only worked by luck: guess a parameter name, write it,
read the error, correct it. The design read-back grades the destination; this
grades the route, which is what predicts whether the next run lands in the same
place.

The rule is one ordering constraint: **every mutating call must be preceded by a
discovery call in an earlier tool call.** "Earlier" is load-bearing -- discovery
text sitting in the *same* script as the mutation cannot have informed it, since
the whole script was written before any of its output existed. A single call
that both discovers and mutates is therefore a violation *unless* it matches a
``combined_patterns`` entry, which marks a helper that consumes its own
discovery internally (the ip-configurator's ``ipcfg::configure_feature`` does
identity -> discovery -> shape -> apply -> verify inside one call, so its
mutation is discovery-informed by construction).

Why this exists as a separate grader rather than an ``action_sequence`` spec:
``action_sequence`` matches a tool-call sequence against an expected list, so
expressing "any of these discovery calls, at least once, before the first of
these mutating calls, where one helper counts as both" would need an expected
sequence per case and still could not express the ordering as a constraint.

Generic infra: every pattern is supplied by the suite's ``grader_spec.yaml``.
This module knows nothing about Vivado, Tcl, or ``ipcfg`` -- it knows "some
tool-call payloads mean look, others mean write, and looking has to come first".

Spec::

    discovery_first:
      grader: discovery_first
      grader_args:
        tool: vivado_execute          # optional: restrict to one tool
        discovery_patterns: ['ipcfg::find_params', 'list_property', ...]
        mutation_patterns:  ['set_property', 'create_bd_cell']
        combined_patterns:  ['ipcfg::configure_feature']

Patterns are regexes, matched case-insensitively against the call's command
payload (and against the tool name, so a tool can itself be the signal).

Score is the fraction of mutating calls that were discovery-informed; ``passed``
is true when there are no violations. A case with no mutating calls at all
passes with a note rather than dividing by zero -- it is the read-back grader's
job to notice that nothing was built.
"""
from __future__ import annotations

import re
from typing import Any

from . import Grader, GraderContext, GraderResult, register_grader
from .trace import canonical_mcp_name, tool_calls_detailed


def _compile(patterns: Any) -> list[re.Pattern]:
    if patterns is None:
        return []
    if isinstance(patterns, str):
        patterns = [patterns]
    out = []
    for p in patterns:
        try:
            out.append(re.compile(str(p), re.IGNORECASE))
        except re.error:
            # A bad regex in a spec must not take the whole run down; fall back
            # to a literal match on it.
            out.append(re.compile(re.escape(str(p)), re.IGNORECASE))
    return out


def _hits(pats: list[re.Pattern], text: str) -> list[str]:
    return [p.pattern for p in pats if p.search(text)]


class DiscoveryFirstGrader(Grader):
    grader_type = "discovery_first"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        discovery = _compile(spec.get("discovery_patterns"))
        mutation = _compile(spec.get("mutation_patterns"))
        combined = _compile(spec.get("combined_patterns"))
        if not mutation:
            return GraderResult(
                passed=False, score=0.0,
                details={"feedback": "discovery_first: 'mutation_patterns' is "
                                     "required (nothing to check ordering of)"})

        only_tool = spec.get("tool")
        client = ctx.run_meta.get("client")
        aliases = ctx.run_meta.get("mcp_server_aliases")
        calls = tool_calls_detailed(ctx.stdout, ctx.stderr, client=client)

        seen_discovery: list[str] = []
        violations: list[dict] = []
        compliant: list[dict] = []
        n_mut = 0
        checked = 0

        for idx, (name, command) in enumerate(calls, start=1):
            canon = canonical_mcp_name(name, aliases)
            if only_tool and str(only_tool).lower() not in canon.lower():
                continue
            checked += 1
            text = f"{canon}\n{command or ''}"

            comb_hit = _hits(combined, text)
            mut_hit = _hits(mutation, text)
            disc_hit = _hits(discovery, text)

            if comb_hit:
                # Discovers and mutates inside one call, by design.
                n_mut += 1
                compliant.append({"call": idx, "tool": canon,
                                  "why": "combined", "matched": comb_hit})
                seen_discovery.append(f"#{idx}:{comb_hit[0]}")
                continue

            if mut_hit:
                n_mut += 1
                if seen_discovery:
                    compliant.append({"call": idx, "tool": canon,
                                      "why": "preceded by discovery",
                                      "matched": mut_hit,
                                      "after": list(seen_discovery)})
                else:
                    violations.append({
                        "call": idx, "tool": canon, "matched": mut_hit,
                        "why": ("mutating call with no PRIOR discovery call"
                                + (" (discovery in the SAME call cannot have "
                                   "informed it)" if disc_hit else "")),
                        "same_call_discovery": disc_hit,
                        "command": (command or "")[:400],
                    })

            if disc_hit:
                seen_discovery.append(f"#{idx}:{disc_hit[0]}")

        if n_mut == 0:
            return GraderResult(
                passed=True, score=1.0,
                details={"feedback": "no mutating calls observed -- ordering "
                                     "constraint trivially satisfied",
                         "tool_calls_considered": checked,
                         "mutating_calls": 0,
                         "discovery_calls": len(seen_discovery)})

        score = len(compliant) / n_mut
        passed = not violations
        first = violations[0] if violations else None
        feedback = (
            f"{len(compliant)}/{n_mut} mutating calls were discovery-informed"
            if passed else
            f"{len(violations)}/{n_mut} mutating calls wrote before discovering"
            f" -- first at call #{first['call']} ({first['tool']}, matched "
            f"{first['matched']}): {first['why']}"
        )
        return GraderResult(
            passed=passed, score=score,
            details={"feedback": feedback,
                     "tool_calls_considered": checked,
                     "mutating_calls": n_mut,
                     "discovery_calls": len(seen_discovery),
                     "discovery_sequence": seen_discovery,
                     "violations": violations,
                     "compliant": compliant})


register_grader(DiscoveryFirstGrader.grader_type, DiscoveryFirstGrader())
