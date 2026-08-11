#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Independent, DETERMINISTIC correctness gate for the hls-intro-matmul_gen suite.
#
# This does NOT trust results.json. It takes the kernel the agent actually
# produced and recompiles it against the FROZEN testbench (main.cpp — the
# suite's own oracle), runs it, and passes ONLY if the testbench prints PASS.
# Same idea as the skill's Step 2e g++ check, but run by the grader so the agent
# cannot fake it.
#
# Contract (see test_cases.yaml prompt):
#   * arg $1 = which pinned kernel to verify, relative to outputs/<case>/
#       (default: kernel_final.cpp — the final optimized kernel; the architect
#        stage output architect_kernel_hls.cpp is verified with a second call).
#   * the top-level kernel keeps the inputs/kernel.hpp signature
#       void kernel(float C[], const float A[], const float B[], int, int, int)
#     (true for the m_axi pointer interface this design uses), so the frozen
#     testbench can call it directly.
#
# Exit 0  -> PASS (score 1.0)   |   Exit non-zero -> FAIL (score 0.0)
# Everything printed here becomes the grader feedback.
# ─────────────────────────────────────────────────────────────────────────────
set -u

WS="${SKILL_TEST_WORKSPACE_DIR:-${WAZA_WORKSPACE_DIR:-$PWD}}"
CASE="hls-intro-matmul_gen_01"
KERNEL_NAME="${1:-kernel_final.cpp}"           # which pinned kernel to verify

# The harness stages a suite's declared input_files FLAT at the workspace
# root (see core/case_loader.py), so main.cpp / kernel.hpp live directly under
# $WS, not under $WS/inputs.
#
# The ORACLE is taken from the suite's inputs/ pool, not from the workspace: the
# workspace copy is writable by the agent, so grading against it means grading
# against a testbench the agent may have rewritten (an agent on the sibling
# globaltonemapping_gen suite did exactly that when its build broke — see that
# suite's check_testbench_unmodified.sh). Only fall back to the workspace copy
# if the suite pool is unavailable, e.g. when running this script by hand.
SUITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
if [ -n "${SUITE_DIR:-}" ] && [ -f "$SUITE_DIR/inputs/main.cpp" ]; then
    TB="$SUITE_DIR/inputs/main.cpp"            # frozen testbench (the oracle)
    if [ -f "$WS/main.cpp" ] && ! cmp -s "$TB" "$WS/main.cpp"; then
        echo "[gate] WARNING: the workspace main.cpp DIFFERS from the frozen suite input — grading against the frozen copy. The agent modified the testbench."
    fi
else
    echo "[gate] WARNING: frozen inputs/main.cpp not found next to this script; falling back to the workspace copy, which the agent can modify."
    TB="$WS/main.cpp"
fi
HDR_DIR="$WS"                                  # holds kernel.hpp
OUT_DIR="$WS/outputs/$CASE"
KERNEL="$OUT_DIR/$KERNEL_NAME"                 # agent's produced kernel

M=64; N=64; K=64

fail() { echo "CORRECTNESS-GATE FAIL: $*"; exit 1; }

# ── Preconditions ────────────────────────────────────────────────────────────
[ -f "$TB" ]     || fail "frozen testbench missing at $TB"
[ -f "$KERNEL" ] || fail "agent kernel missing at $KERNEL — the agent must copy this kernel to outputs/$CASE/$KERNEL_NAME"
[ -n "${XILINX_VITIS:-}" ] || fail "XILINX_VITIS not set — cannot locate ap_float.h / HLS software headers needed to compile the testbench"
[ -f "$XILINX_VITIS/include/ap_float.h" ] || fail "ap_float.h not found under \$XILINX_VITIS/include ($XILINX_VITIS/include)"

TMPDIR_GATE="$(mktemp -d)"
BIN="$TMPDIR_GATE/verify_matmul"
trap 'rm -rf "$TMPDIR_GATE"' EXIT

# ── Compile: agent kernel + FROZEN testbench ─────────────────────────────────
echo "[gate] compiling agent kernel against frozen testbench"
echo "[gate]   kernel   : $KERNEL"
echo "[gate]   testbench: $TB"
CC_LOG="$TMPDIR_GATE/compile.log"
if ! g++ -std=c++14 \
      -I"$XILINX_VITIS/include" \
      -I"$HDR_DIR" \
      -I"$OUT_DIR" \
      -o "$BIN" "$KERNEL" "$TB" >"$CC_LOG" 2>&1; then
    echo "----- g++ output -----"; cat "$CC_LOG"; echo "----------------------"
    fail "g++ failed to compile the agent kernel with the frozen testbench (signature/interface mismatch or non-synthesizable-for-g++ code)"
fi

# ── Run the testbench ────────────────────────────────────────────────────────
echo "[gate] running testbench at ${M}x${N}x${K}"
RUN_OUT="$("$BIN" "$M" "$N" "$K" 2>&1)"; RC=$?
echo "----- testbench output -----"
echo "$RUN_OUT"
echo "----------------------------"

# ── Verdict (uses main.cpp's own PASS/FAIL, not results.json) ─────────────────
[ $RC -eq 0 ] || fail "testbench exited non-zero (rc=$RC)"
echo "$RUN_OUT" | grep -q "FAIL" && fail "testbench printed FAIL — agent kernel does not match the reference"
echo "$RUN_OUT" | grep -q "PASS" || fail "testbench did not print PASS (no PASS line found)"

echo "CORRECTNESS-GATE PASS: agent kernel matches the reference under the frozen testbench"
exit 0
