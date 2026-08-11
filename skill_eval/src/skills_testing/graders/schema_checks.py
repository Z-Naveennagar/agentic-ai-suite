"""
Declarative schema-check primitives consumed by the report_schema grader.

A schema YAML is a list of named checks. Each check has a `type` that
maps to one of the callables in CHECK_REGISTRY. Callable signature:

    check(text: str, params: dict, ctx: dict) -> {
        "passed":  bool,
        "details": dict,        # arbitrary, surfaces in grader output
    }

`ctx` is a small dict the report_schema grader passes through so checks
can reference manifest parameters / run metadata via `{{ var.name }}`
template substitution. We deliberately keep templating to a flat
key=value dict to avoid depending on jinja2 in the test runner.
"""

from __future__ import annotations

import re
from typing import Any, Callable


CHECK_REGISTRY: dict[str, Callable[[str, dict, dict], dict]] = {}


def register_check(name: str, fn: Callable[[str, dict, dict], dict]) -> None:
    CHECK_REGISTRY[name] = fn


def get_check(name: str) -> Callable[[str, dict, dict], dict]:
    if name not in CHECK_REGISTRY:
        raise KeyError(f"unknown schema check: {name!r}")
    return CHECK_REGISTRY[name]


# -- template substitution -------------------------------------------------

_TMPL = re.compile(r"\{\{\s*([\w\.]+)\s*\}\}")


def render(value: Any, vars_: dict) -> Any:
    """Recursively expand {{ var.name }} placeholders in str/list/dict."""
    if isinstance(value, str):
        return _TMPL.sub(lambda m: str(_lookup(vars_, m.group(1))), value)
    if isinstance(value, list):
        return [render(v, vars_) for v in value]
    if isinstance(value, dict):
        return {k: render(v, vars_) for k, v in value.items()}
    return value


def _lookup(vars_: dict, dotted: str) -> Any:
    cur: Any = vars_
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return ""
    return cur


# -- check primitives ------------------------------------------------------


def regex_required(text: str, params: dict, ctx: dict) -> dict:
    pat = params["pattern"]
    flags = re.MULTILINE | (re.IGNORECASE if params.get("ignore_case") else 0)
    m = re.search(pat, text, flags)
    return {"passed": m is not None,
            "details": {"pattern": pat, "match": m.group(0) if m else None}}


def regex_forbidden(text: str, params: dict, ctx: dict) -> dict:
    pat = params["pattern"]
    flags = re.MULTILINE | (re.IGNORECASE if params.get("ignore_case") else 0)
    m = re.search(pat, text, flags)
    return {"passed": m is None,
            "details": {"pattern": pat, "match": m.group(0) if m else None}}


def any_of_regex(text: str, params: dict, ctx: dict) -> dict:
    pats = params["patterns"]
    flags = re.MULTILINE | (re.IGNORECASE if params.get("ignore_case") else 0)
    matched = [p for p in pats if re.search(p, text, flags)]
    return {"passed": bool(matched),
            "details": {"patterns": pats, "matched": matched}}


def all_of_regex(text: str, params: dict, ctx: dict) -> dict:
    pats = params["patterns"]
    flags = re.MULTILINE | (re.IGNORECASE if params.get("ignore_case") else 0)
    missing = [p for p in pats if not re.search(p, text, flags)]
    return {"passed": not missing,
            "details": {"patterns": pats, "missing": missing}}


def required_substrings(text: str, params: dict, ctx: dict) -> dict:
    needed = params["substrings"]
    case = bool(params.get("case_sensitive", True))
    hay = text if case else text.lower()
    missing = [s for s in needed
               if (s if case else s.lower()) not in hay]
    return {"passed": not missing,
            "details": {"missing": missing, "required": needed}}


def forbidden_substrings(text: str, params: dict, ctx: dict) -> dict:
    forbidden = params["substrings"]
    case = bool(params.get("case_sensitive", True))
    hay = text if case else text.lower()
    found = [s for s in forbidden
             if (s if case else s.lower()) in hay]
    return {"passed": not found,
            "details": {"found": found, "forbidden": forbidden}}


def required_headings(text: str, params: dict, ctx: dict) -> dict:
    """
    Each heading is matched as a whole-line, leading-whitespace-tolerant
    substring (case-insensitive by default). Useful for Vivado-style
    section headers like '1. Design Timing Summary'.
    """
    headings = params["headings"]
    case = bool(params.get("case_sensitive", False))
    lines = text.splitlines()
    hay = [(ln if case else ln.lower()).strip() for ln in lines]
    missing: list[str] = []
    for h in headings:
        needle = h if case else h.lower()
        if not any(needle in ln for ln in hay):
            missing.append(h)
    return {"passed": not missing,
            "details": {"missing": missing, "required": headings}}


def required_columns(text: str, params: dict, ctx: dict) -> dict:
    """
    Verify a table-style report contains a header row that mentions each
    of the named columns. Two formats are accepted:

      1. Pipe-separated (Markdown-style) tables -- fields between '|'.
      2. Whitespace-aligned tables (Vivado's native ``report_timing_summary``
         text output and similar). The header may also wrap across two
         consecutive lines, e.g.::

             WNS    TNS Failing  TNS Total
             (ns)   Endpoints    Endpoints

         is treated as the merged header
         ``WNS (ns) | TNS Failing | TNS Total ...``.

    A column is considered present if its normalized form (whitespace
    collapsed) appears as a substring inside any one of the parsed cells
    of a single (possibly merged) header row, or appears as a substring
    of the merged-line text.
    """
    cols = params["columns"]
    case = bool(params.get("case_sensitive", False))

    def _norm(s: str) -> str:
        s = re.sub(r"\s+", " ", s).strip()
        return s if case else s.lower()

    wanted = [_norm(c) for c in cols]
    lines = text.splitlines()

    def _check_cells(cells: list[str], merged: str) -> bool:
        norm_cells = [_norm(c) for c in cells if c.strip()]
        norm_merged = _norm(merged)
        for w in wanted:
            if any(w in c for c in norm_cells):
                continue
            if w in norm_merged:
                continue
            return False
        return True

    for idx, line in enumerate(lines):
        if not line.strip():
            continue

        if "|" in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if _check_cells(cells, line):
                return {"passed": True,
                        "details": {"row": line.strip(), "matched": cols,
                                    "format": "pipe"}}

        cells_ws = re.split(r"\s{2,}", line.strip())
        if len(cells_ws) >= 2 and _check_cells(cells_ws, line):
            return {"passed": True,
                    "details": {"row": line.strip(), "matched": cols,
                                "format": "whitespace"}}

        if idx + 1 < len(lines):
            nxt = lines[idx + 1]
            if nxt.strip() and not re.fullmatch(r"[\s\-=_+|]+", nxt):
                cells_a = re.split(r"\s{2,}", line.strip())
                cells_b = re.split(r"\s{2,}", nxt.strip())
                if (len(cells_a) >= 2 and len(cells_a) == len(cells_b)):
                    merged_cells = [
                        f"{a.strip()}{b.strip()}" if (b.strip().startswith("(")
                                                     or a.strip().endswith(("(", ")")))
                        else f"{a.strip()} {b.strip()}"
                        for a, b in zip(cells_a, cells_b)
                    ]
                    merged_text = " | ".join(merged_cells)
                    if _check_cells(merged_cells, merged_text):
                        return {"passed": True,
                                "details": {"row": merged_text,
                                            "matched": cols,
                                            "format": "whitespace_wrapped"}}

    return {"passed": False,
            "details": {"required": cols, "reason": "no header row matched"}}


def tcl_well_formed(text: str, params: dict, ctx: dict) -> dict:
    """Re-uses tcl_syntax_check semantics inline (no I/O)."""
    pairs = {"{": "}", "[": "]", "(": ")"}
    closers = {v: k for k, v in pairs.items()}
    stack: list[str] = []
    in_comment = False
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\n":
            in_comment = False
            i += 1
            continue
        if in_comment:
            i += 1
            continue
        if c == "\\" and i + 1 < len(text):
            i += 2
            continue
        if c == '"':
            in_string = not in_string
            i += 1
            continue
        if in_string:
            i += 1
            continue
        if c == "#" and (i == 0 or text[i - 1] in " \t\n;"):
            in_comment = True
            i += 1
            continue
        if c in pairs:
            stack.append(c)
        elif c in closers:
            if not stack or stack[-1] != closers[c]:
                return {"passed": False,
                        "details": {"reason": f"unbalanced {c!r} at offset {i}"}}
            stack.pop()
        i += 1
    if stack:
        return {"passed": False,
                "details": {"reason": "unclosed", "open": stack}}
    return {"passed": True, "details": {"chars": len(text)}}


def min_line_count(text: str, params: dict, ctx: dict) -> dict:
    n = sum(1 for ln in text.splitlines() if ln.strip())
    threshold = int(params["min"])
    return {"passed": n >= threshold,
            "details": {"non_empty_lines": n, "min": threshold}}


def regex_capture_in_range(text: str, params: dict, ctx: dict) -> dict:
    """Capture group 1 must parse as float and lie in [min, max]."""
    pat = params["pattern"]
    flags = re.MULTILINE | (re.IGNORECASE if params.get("ignore_case") else 0)
    m = re.search(pat, text, flags)
    if not m:
        return {"passed": False, "details": {"reason": "no_match", "pattern": pat}}
    try:
        v = float(m.group(1))
    except (ValueError, IndexError):
        return {"passed": False,
                "details": {"reason": "no_capture_group", "match": m.group(0)}}
    lo = params.get("min")
    hi = params.get("max")
    ok = (lo is None or v >= float(lo)) and (hi is None or v <= float(hi))
    return {"passed": ok,
            "details": {"value": v, "min": lo, "max": hi, "match": m.group(0)}}


# -- registration ---------------------------------------------------------

for _n, _fn in (
    ("regex_required", regex_required),
    ("regex_forbidden", regex_forbidden),
    ("any_of_regex", any_of_regex),
    ("all_of_regex", all_of_regex),
    ("required_substrings", required_substrings),
    ("forbidden_substrings", forbidden_substrings),
    ("required_headings", required_headings),
    ("required_columns", required_columns),
    ("tcl_well_formed", tcl_well_formed),
    ("min_line_count", min_line_count),
    ("regex_capture_in_range", regex_capture_in_range),
):
    register_check(_n, _fn)
