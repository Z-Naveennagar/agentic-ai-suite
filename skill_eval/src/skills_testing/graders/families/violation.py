"""
``violation`` family — "did the agent correctly classify / flag issues?"

The generalized HLS-verdict pattern. The author states the expected verdict
(and optionally cited rule IDs and/or a ground-truth oracle); the family emits
the core graders that check the verdict line is present, the opposite verdict
is absent, the rules are cited, and the categories match the oracle.

Author YAML::

    - family: violation
      id: verdict
      verdict: NO                            # expected answer (required)
      verdict_source: stdout                 # default stdout
      verdict_regex: '(?i)VERDICT:\\s*{verdict}\\b'   # {verdict} is substituted
      opposite: YES                          # optional; inferred for YES/NO
      rules: ["6.2", "6.3"]                  # optional cited rule IDs
      oracle: case://oracle/expected.yaml    # optional ground-truth file
      artifact: outputs/classification.txt   # optional artifact for oracle_match
"""

from __future__ import annotations

import re

from . import Family, register_family

_DEFAULT_VERDICT_REGEX = r"(?i)VERDICT:\s*{verdict}\b"
_OPPOSITE = {"yes": "NO", "no": "YES"}


def _coerce_verdict(value) -> str:
    """Normalize the author's verdict to a string.

    YAML 1.1 parses unquoted ``YES``/``NO``/``ON``/``OFF`` as booleans, so a
    spec written ``verdict: NO`` arrives here as ``False``. Map booleans back
    to the YES/NO vocabulary so authors don't have to remember to quote it.
    """
    if isinstance(value, bool):
        return "YES" if value else "NO"
    return str(value)


class ViolationFamily(Family):
    family_type = "violation"
    required = ("verdict",)

    def expand(self, params: dict, meta: dict) -> list[dict]:
        verdict = _coerce_verdict(params["verdict"])
        source = params.get("verdict_source", "stdout")
        tmpl = params.get("verdict_regex", _DEFAULT_VERDICT_REGEX)

        def _regex_for(value: str) -> str:
            # Substitute {verdict} only; .replace avoids choking on regex
            # braces like \d{2} that .format() would misinterpret.
            return tmpl.replace("{verdict}", re.escape(value))

        specs: list[dict] = [{
            "id": "verdict_present",
            "type": "content_contains",
            "source": source,
            "regex": _regex_for(verdict),
        }]

        opposite = params.get("opposite") or _OPPOSITE.get(verdict.lower())
        if opposite:
            specs.append({
                "id": "verdict_not_opposite",
                "type": "content_contains",
                "source": source,
                "regex": _regex_for(str(opposite)),
                "must_not_contain": True,
            })

        for i, rule in enumerate(params.get("rules") or [], start=1):
            specs.append({
                "id": f"rule_{i}",
                "type": "content_contains",
                "source": source,
                "regex": rf"(?i)RULES:[^\n]*{re.escape(str(rule))}",
            })

        if params.get("oracle"):
            oracle_spec = {
                "id": "oracle_categories",
                "type": "oracle_match",
                "oracle": params["oracle"],
                "match_rules": [
                    {"kind": "every_oracle_endpoint_referenced",
                     "from_oracle": params.get("required_categories_key",
                                               "required_categories")},
                    {"kind": "regex_must_not_appear",
                     "patterns_from_oracle": params.get("forbidden_categories_key",
                                                        "forbidden_categories")},
                ],
            }
            if params.get("artifact"):
                oracle_spec["artifact"] = params["artifact"]
            specs.append(oracle_spec)

        return specs


register_family(ViolationFamily())
