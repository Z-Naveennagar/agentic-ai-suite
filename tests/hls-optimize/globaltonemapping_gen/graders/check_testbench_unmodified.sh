#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Independent TESTBENCH-INTEGRITY gate for the globaltonemapping_gen suite.
#
# WHY THIS EXISTS
# ---------------
# Every correctness signal in this suite is downstream of ONE assumption: that
# the verdict line in csim.log ("Test Passed" / "ERROR: Test Failed.") was
# printed by the suite's OWN testbench, comparing the kernel against an OpenCV
# software reference on the real input image. If the agent edits
# xf_gtm_tb.cpp, that assumption silently dies and csim_log_pass degrades into
# "the agent printed the string we grep for".
#
# This is not hypothetical. In run 8c6d64c1 (azure/gpt-5.4) the agent could not
# locate OpenCV, concluded the host lacked it, and did exactly this:
#   "I'm making the minimum host-side edits needed to unblock real HLS runs in
#    this environment: remove the OpenCV dependency from the testbench/config
#    while preserving the same input image, software-reference check, and
#    verdict line."
# It replaced the oracle with one of its own construction. A rewritten
# testbench that still prints "Test Passed" would satisfy csim_log_pass,
# csim_log_no_failure and test_passed simultaneously — the suite's entire
# correctness story — while never having run the reference comparison.
#
# A full recompile-and-rerun gate (matmul's correctness_recompiled) is not
# practical here: it needs OpenCV plus a Versal toolchain. Integrity checking
# the oracle is the affordable equivalent — it cannot prove the kernel correct,
# but it restores the meaning of the gates that do.
#
# WHAT IS AND IS NOT CHECKED
# --------------------------
# Only xf_gtm_tb.cpp is frozen — the file holding the reference comparison and
# the verdict lines. The agent is *supposed* to edit the kernel and its config
# (xf_gtm_accel.cpp, xf_config_params.h, xf_gtm_accel_config.h) to raise NPPC
# and widen ports, and xf_gtm_tb_config.h carries NPPC-dependent typedefs the
# testbench needs to keep compiling, so none of those are gated here.
#
# Exit 0 -> PASS (score 1.0)   |   Exit non-zero -> FAIL (score 0.0)
# ─────────────────────────────────────────────────────────────────────────────
set -u

WS="${SKILL_TEST_WORKSPACE_DIR:-${WAZA_WORKSPACE_DIR:-$PWD}}"
TB_NAME="xf_gtm_tb.cpp"

# The frozen master lives in the suite's own inputs/ pool, NOT in the workspace
# (the workspace copy is the one the agent can edit). This script is executed
# from the installed suite dir, so resolve inputs/ relative to the script.
SUITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FROZEN="$SUITE_DIR/inputs/$TB_NAME"
STAGED="$WS/$TB_NAME"

fail() { echo "TESTBENCH-INTEGRITY-GATE FAIL: $*"; exit 1; }

[ -f "$FROZEN" ] || fail "frozen reference testbench missing at $FROZEN — cannot verify integrity (suite install problem, not an agent problem)"
[ -f "$STAGED" ] || fail "testbench missing from the workspace at $STAGED — the agent deleted or moved $TB_NAME"

echo "[gate] frozen testbench : $FROZEN"
echo "[gate] workspace copy   : $STAGED"

if cmp -s "$FROZEN" "$STAGED"; then
    echo "TESTBENCH-INTEGRITY-GATE PASS: $TB_NAME is byte-identical to the frozen suite input — the csim verdict came from the real OpenCV reference comparison"
    exit 0
fi

echo "[gate] DIFF (frozen -> workspace), first 40 lines:"
diff -u "$FROZEN" "$STAGED" | head -40

# Call out the specific substitution seen in run 8c6d64c1, since a dropped
# OpenCV dependency is the tell that the reference comparison itself is gone.
if ! grep -q 'analyzeDiff' "$STAGED" 2>/dev/null; then
    echo "[gate] NOTE: the workspace testbench no longer calls xf::cv::analyzeDiff — the software-reference comparison has been removed outright."
fi
if ! grep -q 'imread' "$STAGED" 2>/dev/null; then
    echo "[gate] NOTE: the workspace testbench no longer calls cv::imread — it is no longer reading the real input image."
fi

fail "$TB_NAME was MODIFIED. It is the correctness oracle: its verdict line is what csim_log_pass/csim_log_no_failure/test_passed all read, so any edit makes those gates meaningless. Optimize the kernel and its config instead (xf_gtm_accel.cpp, xf_config_params.h, xf_gtm_accel_config.h); leave the testbench alone. If OpenCV appears to be missing, run ./gen_config.sh — it auto-detects it."
