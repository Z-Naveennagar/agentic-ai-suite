"""
Minimal ground-truth read-back of a block-design cell, given only a live
Vivado MCP session id and a cell name.

Run as a ``harness_script`` grader step (see grader_spec.yaml in this suite
dir), AFTER the agent finishes but before ``reset:`` deletes the cell --
grading already happens before reset in the runner's call order, so no
special lifecycle hook is needed for that timing.

Deliberately minimal, by design, not by omission:
  * Requires ``--session-id`` -- it does not fall back to discovering a
    session by working_dir. This suite's group always has a live session by
    the time any case grades (started by runner_spec.yaml's ``setup:``, kept
    alive across the group), so the fallback isn't needed here.
  * Does not recover from a "deferred" (dropped/rejected-but-still-running)
    MCP response the way runtime/vivado_session_setup.py's await_command
    does. A property read-back is a fast, read-only, idempotent query, so
    that failure mode is unlikely to matter in practice; if it does happen,
    this script reports a plain failure/not-found for that one case rather
    than a corrupted shared session (unlike getting it wrong in setup/reset,
    which would poison every later case in the group).
  * Only imports the public MCP transport (skills_testing.verifiers.vivado_mcp)
    -- no reach into other runtime/ modules' private helpers. That's what
    lets this script live here, in the suite's own scripts/ directory,
    instead of in skills_testing/runtime/ alongside the session setup/reset
    helpers it deliberately does NOT depend on.

Writes ``outputs/as_built.json`` (relative to --working-dir) in the same
shape a future ``config_match`` grader step would expect::

    {"identified_ip": "axi_gpio",
     "vlnv": "xilinx.com:ip:axi_gpio:2.0",
     "found": true,
     "as_configured": {"CONFIG.C_GPIO_WIDTH": "16", ...}}

Only params the customization actually CHANGED are recorded (``VALUE_SRC !=
DEFAULT``), not every ``CONFIG.*`` -- that's both what "what you actually
set" grading needs and what keeps a large IP (e.g. Versal CIPS/ps11,
thousands of defaults) from producing a huge payload.

Usage (see grader_spec.yaml)::

    python vivado_bd_readback.py \\
        --cell=bench_cell_001 \\
        --session-id=<live session id> \\
        --out=outputs/as_built.json \\
        --working-dir=<case workspace>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Optional

from skills_testing.verifiers.vivado_mcp import MCPSession, extract_text, server_url

#: Last line the read-back TCL prints on success -- the authoritative
#: success signal this script waits for.
READBACK_DONE_SENTINEL = "READBACK_DONE"
_NOTFOUND_SENTINEL = "READBACK_CELL_NOT_FOUND"

# Tab-delimited so a CONFIG value containing "="/":"/spaces (common) survives
# the round-trip; keys/values never contain a literal tab.
_VLNV_PREFIX = "READBACK_VLNV\t"
_CFG_PREFIX = "READBACK_CFG\t"

#: Cap on synthesized nested-dict leaf entries (see :func:`_flatten_nested`).
#: Deliberately generous -- it bounds only the size of the local JSON
#: artifact, not the MCP payload (the container's value arrives from Vivado
#: as one string regardless). Set too low, it causes false FAILURES: a case
#: that applies a full Versal PS config can have ~1700+ sub-keys in one
#: container, and a tight cap can truncate before reaching the one the
#: golden actually asks about, making a correct design look wrong.
_DEFAULT_MAX_LEAVES = 5000

#: A dict sub-key must look like a parameter name for a value to be treated
#: as a bundle; this is what stops an ordinary multi-word string value from
#: being shredded into bogus leaves.
_PARAM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def build_tcl(*, cell: str, nonce: str) -> str:
    """Render the read-back TCL: locate *cell*, emit its VLNV and every
    ``CONFIG.*`` property the customization actually changed
    (``VALUE_SRC != DEFAULT``), then ``READBACK_DONE``.

    Field delimiter is a real tab built with ``[format %c 9]`` at runtime,
    not a ``"\\t"`` escape -- the MCP transport rewrites a literal backslash
    in command text, so a backslash-escaped delimiter doesn't survive.
    """
    return "\n".join([
        "# harness read-back (ip-configurator scripts/vivado_bd_readback.py)",
        f"# readback-nonce: {nonce}",  # MCP dedupes vivado_execute by command
                                       # text; the nonce keeps repeat reads
                                       # of the same cell from being replayed.
        "set _T [format %c 9]",
        f"set _cell [lindex [get_bd_cells -quiet {cell}] 0]",
        "if {$_cell eq \"\"} {",
        f'    puts "{_NOTFOUND_SENTINEL}"',
        f'    puts "{READBACK_DONE_SENTINEL}"',
        "} else {",
        f'    puts "{_VLNV_PREFIX.rstrip(chr(9))}${{_T}}[get_property VLNV $_cell]"',
        "    foreach _p [lsort [list_property $_cell]] {",
        '        if {[string match "CONFIG.*" $_p]} {',
        '            set _src {}',
        "            catch {set _src [get_property $_p.VALUE_SRC $_cell]}",
        '            if {$_src ne "DEFAULT"} {',
        f'                puts "{_CFG_PREFIX.rstrip(chr(9))}${{_T}}$_p${{_T}}[get_property $_p $_cell]"',
        "            }",
        "        }",
        "    }",
        f'    puts "{READBACK_DONE_SENTINEL}"',
        "}",
    ])


def _inner_output(exec_text: str) -> str:
    """``vivado_execute`` wraps its result as a JSON envelope
    ``{"exit_code": N, "output": "<puts stream>"}`` in the tool's text
    content. Decode it to get real newlines/tabs back; fall back to the
    text as-is if it isn't that envelope."""
    if not exec_text:
        return ""
    brace = exec_text.find("{")
    if brace >= 0:
        try:
            obj = json.loads(exec_text[brace:])
        except (ValueError, json.JSONDecodeError):
            obj = None
        if isinstance(obj, dict) and "output" in obj:
            return str(obj.get("output") or "")
    return exec_text


def _parse_readback(text: str) -> tuple[Optional[str], dict[str, str], bool]:
    vlnv: Optional[str] = None
    cfg: dict[str, str] = {}
    found = _NOTFOUND_SENTINEL not in text
    for raw in text.splitlines():
        if raw.startswith(_VLNV_PREFIX):
            vlnv = raw[len(_VLNV_PREFIX):].strip()
        elif raw.startswith(_CFG_PREFIX):
            fields = raw[len(_CFG_PREFIX):].split("\t")
            if len(fields) >= 2:
                cfg[fields[0].strip()] = "\t".join(fields[1:])
    return vlnv, cfg, found


def _tcl_split(value: str) -> Optional[list[str]]:
    """Split a flat Tcl list into elements, stripping one level of quoting.

    Returns ``None`` when *value* is not a well-formed Tcl list (unbalanced
    braces or quotes), so a plain string is never mistaken for a bundle.
    """
    out: list[str] = []
    i, n = 0, len(value)
    while i < n:
        while i < n and value[i] in " \t\n":
            i += 1
        if i >= n:
            break
        if value[i] == "{":
            depth, j = 1, i + 1
            while j < n and depth:
                if value[j] == "{":
                    depth += 1
                elif value[j] == "}":
                    depth -= 1
                j += 1
            if depth:
                return None
            out.append(value[i + 1:j - 1])
            i = j
        elif value[i] == '"':
            j = i + 1
            while j < n and value[j] != '"':
                j += 2 if value[j] == "\\" else 1
            if j >= n:
                return None
            out.append(value[i + 1:j])
            i = j + 1
        else:
            j = i
            while j < n and value[j] not in " \t\n":
                j += 1
            out.append(value[i:j])
            i = j
    return out


def _dict_pairs(key: str, value: str) -> Optional[list[tuple[str, str]]]:
    """Return *value* as ``(sub-key, sub-value)`` pairs, or ``None``.

    Two guards keep ordinary values out: the value must either contain a
    braced element or sit on a ``*_CONFIG``-named param (both true of the
    subsystem containers this exists for), and every sub-key must look like
    a parameter name.
    """
    if "{" not in value and not key.endswith("_CONFIG"):
        return None
    elems = _tcl_split(value)
    if not elems or len(elems) < 2 or len(elems) % 2:
        return None
    pairs = list(zip(elems[0::2], elems[1::2]))
    if not all(_PARAM_NAME_RE.match(k) for k, _ in pairs):
        return None
    return pairs


def _flatten_nested(
    cfg: dict[str, str], max_leaves: int = _DEFAULT_MAX_LEAVES,
) -> tuple[list[str], bool]:
    """Add leaf entries for every nested-dict ``CONFIG.*`` value in *cfg*.

    Subsystem IPs (e.g. the Versal PS) expose their real parameters as
    sub-keys of one dict-valued property rather than as flat properties --
    e.g. the CAN-FD parameters exist only inside ``CONFIG.PS11_CONFIG`` on
    some Vivado versions. Recording just the container makes a correct
    configuration unreadable to a grader whose golden names the leaf.

    Each sub-key is emitted under BOTH spellings -- ``CONFIG.X(SUB)``
    (explicit about the nesting) and the bare ``CONFIG.SUB`` (what a flat
    golden names) -- so goldens written against either shape match without
    grader changes. A leaf never overwrites a real property of the same
    name, and *max_leaves* bounds the total. Mutates *cfg*; returns
    ``(leaf_keys, truncated)``.
    """
    add_cfg: dict[str, str] = {}
    leaves: list[str] = []
    truncated = False
    for key in list(cfg):
        pairs = _dict_pairs(key, cfg[key])
        if not pairs:
            continue
        for sub, val in pairs:
            if len(leaves) >= max_leaves:
                truncated = True
                break
            for leaf in (f"{key}({sub})", f"CONFIG.{sub}"):
                # Never shadow a genuine top-level property, and let the
                # first container that supplies a leaf win.
                if leaf in cfg or leaf in add_cfg:
                    continue
                add_cfg[leaf] = val
                leaves.append(leaf)
        if truncated:
            break
    cfg.update(add_cfg)
    return leaves, truncated


def _identified_ip_from_vlnv(vlnv: Optional[str]) -> Optional[str]:
    if not vlnv:
        return None
    parts = vlnv.split(":")
    return parts[2] if len(parts) >= 3 else None


def read_back(
    *, cell: str, session_id: str, out_path: Path,
    timeout_seconds: int = 60, url: Optional[str] = None,
) -> tuple[bool, str]:
    """Read *cell* back over the given live session, write ``as_built.json``.

    Returns ``(ok, detail)``. The session is never started/stopped here --
    it belongs to the group and outlives this one read.
    """
    sess = MCPSession(url or server_url(), timeout_seconds)
    try:
        try:
            sess.initialize()
        except Exception as exc:
            return False, f"MCP init failed against {url or server_url()}: {exc}"

        tcl = build_tcl(cell=cell, nonce=uuid.uuid4().hex)
        exec_res = sess.call(
            "vivado_execute", {"session_id": session_id, "command": tcl})
        exec_text = extract_text(exec_res)

        if READBACK_DONE_SENTINEL not in exec_text:
            return False, f"read-back TCL did not complete:\n{exec_text}"

        vlnv, cfg, found = _parse_readback(_inner_output(exec_text))
        leaves, truncated = _flatten_nested(cfg)
        artifact = {
            "identified_ip": _identified_ip_from_vlnv(vlnv),
            "vlnv": vlnv,
            "cell": cell,
            "found": found,
            "as_configured": cfg,
            # Leaves synthesized from nested dict containers, so a reader
            # can tell a real property from a flattened sub-key.
            "flattened_leaves": leaves,
            "flatten_truncated": truncated,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, indent=2, default=str))
        return True, (
            f"wrote {out_path} (found={found}, "
            f"{len(cfg)} configured CONFIG.* props "
            f"[incl. {len(leaves)} nested leaves"
            f"{', TRUNCATED' if truncated else ''}], vlnv={vlnv})"
        )
    finally:
        sess.close()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="vivado_bd_readback",
        description="Read a block-design cell's VLNV + CONFIG.* back from a "
                    "live Vivado MCP session, given only --session-id and "
                    "--cell, and write as_built.json.")
    ap.add_argument("--cell", required=True,
                    help="Block-design cell to read back, e.g. bench_cell_001.")
    ap.add_argument("--session-id", required=True,
                    help="Live Vivado MCP session id to read from.")
    ap.add_argument("--out", default="outputs/as_built.json",
                    help="Artifact path, relative to --working-dir "
                         "(default: %(default)s)")
    ap.add_argument("--working-dir", default=".",
                    help="Root --out is resolved against (default: cwd, "
                         "which the harness sets to the case's workspace).")
    ap.add_argument("--timeout-seconds", type=int, default=60)
    args = ap.parse_args(argv)

    working_dir = Path(args.working_dir)
    out = Path(args.out)
    if not out.is_absolute():
        out = working_dir / out

    ok, detail = read_back(
        cell=args.cell, session_id=args.session_id, out_path=out,
        timeout_seconds=args.timeout_seconds,
    )
    print(detail)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
