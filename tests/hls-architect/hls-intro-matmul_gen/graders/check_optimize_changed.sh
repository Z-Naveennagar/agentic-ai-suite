#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Independent gate: prove /hls-optimize actually TRANSFORMED the design.
#
# The suite pins two kernels:
#   architect_kernel_hls.cpp  — the /hls-architect stage output (forbidden the
#                               fine-grained pragmas; see architect_pragma_audit)
#   kernel_final.cpp          — the /hls-optimize tuned final kernel
#
# If the two are byte-identical, /hls-optimize did nothing (or was skipped) even
# if the chain reported success. This gate FAILS in that case. It reads only the
# two pinned artifacts, so it cannot be faked via results.json.
#
# Exit 0 -> PASS (score 1.0)   |   Exit non-zero -> FAIL (score 0.0)
# ─────────────────────────────────────────────────────────────────────────────
set -u

WS="${SKILL_TEST_WORKSPACE_DIR:-${WAZA_WORKSPACE_DIR:-$PWD}}"
CASE="hls-intro-matmul_gen_01"
OUT_DIR="$WS/outputs/$CASE"

ARCH="$OUT_DIR/architect_kernel_hls.cpp"
FINAL="$OUT_DIR/kernel_final.cpp"

fail() { echo "OPTIMIZE-CHANGED-GATE FAIL: $*"; exit 1; }

[ -f "$ARCH" ]  || fail "architect stage kernel missing at $ARCH"
[ -f "$FINAL" ] || fail "final kernel missing at $FINAL"

echo "[gate] architect kernel : $ARCH"
echo "[gate] final kernel     : $FINAL"

if diff -q "$ARCH" "$FINAL" >/dev/null 2>&1; then
    fail "kernel_final.cpp is byte-identical to architect_kernel_hls.cpp — /hls-optimize applied no changes"
fi

# Report the size of the change for grader feedback (non-fatal if diff stat fails).
CHANGED_LINES="$(diff "$ARCH" "$FINAL" 2>/dev/null | grep -cE '^[<>]')"
echo "[gate] changed lines (diff <>): ${CHANGED_LINES:-unknown}"
echo "OPTIMIZE-CHANGED-GATE PASS: final kernel differs from the architect stage output"
exit 0
