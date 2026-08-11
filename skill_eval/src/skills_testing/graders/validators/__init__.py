"""
Validator registry consumed by the artifact_valid grader.

A validator is a callable:

    validator(path: pathlib.Path, params: dict) -> {
        "passed":  bool,
        "score":   float,         # optional, defaults to 1.0/0.0 from passed
        "details": dict,          # arbitrary, surfaces in grader output
    }

Real implementations are provided for output shapes used by the in-scope
skills; everything else falls back to a `non_empty_file` stub so the
artifact_valid grader can be wired against any case without breaking.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Callable

VALIDATOR_REGISTRY: dict[str, Callable[[Path, dict], dict]] = {}


def register_validator(name: str, fn: Callable[[Path, dict], dict]) -> None:
    VALIDATOR_REGISTRY[name] = fn


def get_validator(name: str) -> Callable[[Path, dict], dict]:
    if name not in VALIDATOR_REGISTRY:
        raise KeyError(f"unknown validator: {name!r}")
    return VALIDATOR_REGISTRY[name]


# -- non_empty_file --------------------------------------------------------


def non_empty_file(path: Path, params: dict) -> dict:
    min_size = int(params.get("min_size_bytes", 1))
    size = path.stat().st_size
    return {
        "passed": size >= min_size,
        "details": {"size": size, "min_size_bytes": min_size},
    }


# -- tcl_syntax_check ------------------------------------------------------


def tcl_syntax_check(path: Path, params: dict) -> dict:
    """
    Lightweight Tcl sanity check: balance of {}, [] and (), respecting
    line continuations and # comments. This is intentionally not a full
    parser; it catches the common 'forgot a brace' class of error.
    """
    text = path.read_text(errors="replace")
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
        if c == "\\" and i + 1 < len(text):  # escape sequence
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
        kind = "brace" if stack[-1] == "{" else (
            "bracket" if stack[-1] == "[" else "paren")
        return {"passed": False,
                "details": {"reason": f"unbalanced {kind}: {stack[-1]!r} unclosed",
                            "open": stack}}
    return {"passed": True, "details": {"chars": len(text)}}


# -- xclbin_magic_check ----------------------------------------------------


_XCLBIN_MAGICS = (b"xclbin2\x00", b"xclbin\x00")


def xclbin_magic_check(path: Path, params: dict) -> dict:
    head = path.read_bytes()[:16]
    for magic in _XCLBIN_MAGICS:
        if head.startswith(magic):
            return {"passed": True, "details": {"magic": magic.rstrip(b"\x00").decode()}}
    return {"passed": False,
            "details": {"reason": "no xclbin magic", "head_hex": head.hex()}}


# -- bootbin_check ---------------------------------------------------------


def bootbin_check(path: Path, params: dict) -> dict:
    """Very minimal BOOT.BIN sanity check: file is large enough."""
    min_size = int(params.get("min_size_bytes", 1024))
    size = path.stat().st_size
    if size < min_size:
        return {"passed": False,
                "details": {"reason": "too_small", "size": size, "min": min_size}}
    return {"passed": True, "details": {"size": size}}


# -- xsa_archive_check -----------------------------------------------------


def xsa_archive_check(path: Path, params: dict) -> dict:
    """A .xsa is a zip archive that must contain xsa.xml."""
    if not zipfile.is_zipfile(path):
        return {"passed": False, "details": {"reason": "not a zip archive"}}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    if "xsa.xml" not in names:
        return {"passed": False,
                "details": {"reason": "missing xsa.xml", "entries": names[:50]}}
    return {"passed": True, "details": {"entries": names[:50]}}


# -- vivado_methodology_report_parser -------------------------------------


_METH_ROW = re.compile(
    r"^\|\s*([A-Z]+-?\d+)\s*\|\s*([A-Za-z .]+?)\s*\|\s*[^|]+?\|\s*(\d+)\s*\|",
    re.MULTILINE,
)


def vivado_methodology_report_parser(path: Path, params: dict) -> dict:
    text = path.read_text(errors="replace")
    by_rule: dict[str, dict] = {}
    severities: dict[str, int] = {"critical": 0, "warning": 0, "advisory": 0, "other": 0}
    total = 0
    for rule, sev, count in _METH_ROW.findall(text):
        n = int(count)
        total += n
        slug = sev.strip().lower()
        if slug.startswith("critical"):
            severities["critical"] += n
        elif slug.startswith("warning"):
            severities["warning"] += n
        elif slug.startswith("advisory"):
            severities["advisory"] += n
        else:
            severities["other"] += n
        by_rule.setdefault(rule, {"severity": slug, "violations": 0})
        by_rule[rule]["violations"] += n

    max_violations = params.get("max_violations")
    passed = True if max_violations is None else total <= int(max_violations)
    return {
        "passed": passed,
        "details": {
            "total_violations": total,
            "critical_warnings": severities["critical"],
            "warnings": severities["warning"],
            "advisories": severities["advisory"],
            "by_rule": by_rule,
        },
    }


# -- vivado_timing_report_parser ------------------------------------------


_TIMING_HEADER = re.compile(r"WNS\(ns\).*WHS\(ns\)", re.IGNORECASE)
_TIMING_NUM_ROW = re.compile(
    r"\|\s*(-?\d+(?:\.\d+)?)\s*\|"
    r"\s*(-?\d+(?:\.\d+)?)\s*\|"
    r"\s*(-?\d+(?:\.\d+)?)\s*\|"
    r"\s*(-?\d+(?:\.\d+)?)\s*\|"
    r"\s*(-?\d+(?:\.\d+)?)\s*\|"
)


_TIMING_LOOSE_WNS = re.compile(
    r"(?:Worst Negative Slack|WNS)[^\n]{0,40}?(-?\d+(?:\.\d+)?)\s*ns", re.IGNORECASE,
)
_TIMING_LOOSE_HEADER = re.compile(
    r"\b(WNS|TNS|WHS|THS)\b", re.IGNORECASE,
)


def vivado_timing_report_parser(path: Path, params: dict) -> dict:
    text = path.read_text(errors="replace")
    require_positive = params.get("require_positive_slack", True)
    lenient = bool(params.get("lenient", False))

    if _TIMING_HEADER.search(text):
        m = _TIMING_NUM_ROW.search(text)
        if m:
            wns, tns, whs, ths, tpws = (float(x) for x in m.groups())
            passed = (not require_positive) or (wns >= 0 and whs >= 0)
            return {"passed": passed, "details": {
                "wns_ns": wns, "tns_ns": tns, "whs_ns": whs,
                "ths_ns": ths, "tpws_ns": tpws,
            }}

    if lenient and _TIMING_LOOSE_HEADER.search(text):
        wns_match = _TIMING_LOOSE_WNS.search(text)
        wns = float(wns_match.group(1)) if wns_match else None
        passed = (not require_positive) or (wns is not None and wns >= 0)
        return {"passed": passed, "details": {
            "wns_ns": wns,
            "format": "lenient",
            "size": len(text),
        }}

    return {"passed": False, "details": {"reason": "no timing summary row"}}


# -- vivado_cdc_report_parser (lightweight stub) --------------------------


_CDC_SEV = re.compile(r"^\s*(Critical|Warning|Advisory)\b.*?:\s*(\d+)", re.MULTILINE)


def vivado_cdc_report_parser(path: Path, params: dict) -> dict:
    text = path.read_text(errors="replace")
    counts = {"critical": 0, "warning": 0, "advisory": 0}
    for sev, n in _CDC_SEV.findall(text):
        counts[sev.lower()] += int(n)
    max_critical = int(params.get("max_critical", 0))
    passed = counts["critical"] <= max_critical
    return {"passed": passed, "details": counts}


# -- registration ---------------------------------------------------------

for _name, _fn in (
    ("non_empty_file", non_empty_file),
    ("tcl_syntax_check", tcl_syntax_check),
    ("xclbin_magic_check", xclbin_magic_check),
    ("bootbin_check", bootbin_check),
    ("xsa_archive_check", xsa_archive_check),
    ("vivado_methodology_report_parser", vivado_methodology_report_parser),
    ("vivado_timing_report_parser", vivado_timing_report_parser),
    ("vivado_cdc_report_parser", vivado_cdc_report_parser),
):
    register_validator(_name, _fn)
