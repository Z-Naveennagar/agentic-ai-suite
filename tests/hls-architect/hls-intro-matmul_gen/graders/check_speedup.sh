#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Independent, DETERMINISTIC THROUGHPUT gate for the hls-intro-matmul_gen suite.
#
# The example README states the goal as "8x baseline THROUGHPUT". Throughput is
# 1 / Interval (II), NOT 1 / Latency — for the DATAFLOW architecture the skill
# builds, the top-function Interval can be smaller than its Latency (successive
# invocations overlap), so the two metrics genuinely differ. This gate therefore
# parses the "Interval" (max) column out of the two REAL C-synthesis reports the
# agent pinned (baseline_synth.rpt and final_synth.rpt) and computes the
# throughput speedup itself:
#
#       throughput_speedup = baseline_interval / optimized_interval
#
# (lower Interval = higher throughput, so a smaller optimized Interval yields a
# ratio >= 1; pass when it is >= target). It does NOT read results.json, so the
# agent's self-reported number is not trusted.
#
#   $1 = target speedup (default 8)
#
# Requires the reports to contain a NUMERIC Interval. If a report shows "?"
# (unbounded — data-dependent trip counts) the gate FAILS with a clear message:
# the design must be synthesized with bounded trip counts (compile-time sizes or
# #pragma HLS loop_tripcount) for the interval to be estimable.
#
# Exit 0 -> PASS (score 1.0)   |   Exit non-zero -> FAIL (score 0.0)
# ─────────────────────────────────────────────────────────────────────────────
set -u

WS="${SKILL_TEST_WORKSPACE_DIR:-${WAZA_WORKSPACE_DIR:-$PWD}}"
CASE="hls-intro-matmul_gen_01"
TARGET="${1:-8}"

OUT_DIR="$WS/outputs/$CASE"
BASE_RPT="$OUT_DIR/baseline_synth.rpt"
FINAL_RPT="$OUT_DIR/final_synth.rpt"

fail() { echo "THROUGHPUT-GATE FAIL: $*"; exit 1; }

# Vitis emits the top-function Interval in TWO different report layouts, and
# which one lands here depends only on which file the agent copied out of the
# component — both are legitimate answers to the prompt's "save whichever report
# carries the measured top-function Interval". So try both.
#
# LAYOUT A — classic solution-flow "<top>_csynth.rpt":
#   "== Performance Estimates" > "+ Latency:" > "* Summary:" table. Columns
#   (after whitespace is stripped and the row is split on '|'):
#     f[2]=Latency(cyc) min  f[3]=Latency(cyc) max
#     f[4]=Latency(abs) min  f[5]=Latency(abs) max
#     f[6]=Interval min      f[7]=Interval max      f[8]=Pipeline Type
#   We take the Interval MAX (worst-case II) — the throughput-determining number.
extract_interval_classic() {
    awk '
        /== Performance Estimates/      { perf=1 }
        perf && /\+ Latency:/           { lat=1 }
        lat  && /\* Summary:/           { summ=1; next }
        # stop scanning once we leave the summary (Detail section begins)
        summ && /\+ Detail:/            { exit }
        summ && /^[[:space:]]*\|/ {
            line=$0; gsub(/[[:space:]]/,"",line)
            n=split(line, f, "|")   # see column map above
            # first numeric data row: guard on Latency-min being an integer,
            # then emit the Interval-max column.
            if (f[2] ~ /^[0-9]+$/) { print f[7]; exit }
        }
    ' "$1"
}

# LAYOUT B — unified component-flow "== Synthesis Summary Report of '<top>'",
# the "+ Performance & Resource Estimates" Modules & Loops table:
#
#   |+ kernel*        | Timing| -0.55|  237613| 7.841e+05|  -|  237614|  -| dataflow|...
#    ^ top-level module rows start with "|+"; NESTED modules are indented as
#      "| + name" and loops as "| o name", so a bare "|+" prefix uniquely
#      identifies the top function (whose Interval is the one we want).
#
# Column POSITION here is not stable across Vitis versions/targets (a fixed
# f[8] index once silently pointed at the Pipelined column instead of
# Interval, because the real table has extra Violation-Type/Iteration-Latency
# columns before it that an earlier version of this script miscounted — see
# run 398b3102). So don't hardcode an index: read the table's own two-line
# header ("Modules & Loops | Issue Type | Violation Type | Iteration Latency |
# Interval | Trip Count | Pipelined | ...") and find whichever field is
# literally "Interval" after stripping whitespace, then use THAT column
# against the data row. Self-correcting if the table gains/loses columns.
extract_interval_summary() {
    awk '
        /== Synthesis Summary Report/            { insum=1 }
        insum && /Performance & Resource Estim/  { perf=1; next }
        # header rows: "|" immediately followed by anything other than "+"
        # (data rows are "|+top", "| +module", "| o loop"-with-space, all of
        # which either start "|+" or have already set icol by the time we hit
        # them) -- scan until we find the column literally labelled "Interval".
        perf && !icol && /^[[:space:]]*\|[^+]/ {
            line=$0; gsub(/[[:space:]]/,"",line)
            n=split(line, f, "|")
            for (i=1;i<=n;i++) { if (f[i]=="Interval") icol=i }
            next
        }
        perf && icol && /^[[:space:]]*\|\+/ {
            line=$0; gsub(/[[:space:]]/,"",line)
            n=split(line, f, "|")
            if (f[icol] ~ /^[0-9]+$/) { print f[icol]; exit }
        }
    ' "$1"
}

# Prints the integer Interval, or nothing if neither layout yields one.
extract_interval() {
    local v
    v="$(extract_interval_classic "$1")"
    [ -n "$v" ] || v="$(extract_interval_summary "$1")"
    printf '%s' "$v"
}

[ -f "$BASE_RPT" ]  || fail "baseline report missing at $BASE_RPT"
[ -f "$FINAL_RPT" ] || fail "final report missing at $FINAL_RPT"

BASE_II="$(extract_interval "$BASE_RPT")"
FINAL_II="$(extract_interval "$FINAL_RPT")"

echo "[gate] baseline interval/II (cycles) : ${BASE_II:-<none>}"
echo "[gate] optimized interval/II (cycles): ${FINAL_II:-<none>}"
echo "[gate] target throughput speedup     : ${TARGET}x"

# Distinguish "the agent pinned something that is not a Vitis report" from "the
# report is real but its Interval is '?'/'-' (unbounded)". Both land here, but
# they need different fixes, and conflating them made the failure unreadable:
# in run 8c99c6a1 the agent pinned a hand-written narrative of DERIVED numbers
# (because Vitis printed '-' for the top Interval) and the gate reported it as
# an unbounded-trip-count problem.
looks_like_report() {
    grep -qE '== (Performance Estimates|Synthesis Summary Report)' "$1"
}

if [ -z "$BASE_II" ]; then
    if ! looks_like_report "$BASE_RPT"; then
        fail "$BASE_RPT is not a Vitis C-synthesis report — pin the REAL report the flow generated (e.g. <component>/hls/syn/report/csynth.rpt), not a hand-written summary of derived numbers. This gate re-measures the Interval itself and cannot verify arithmetic you did by hand."
    fi
    fail "could not read a numeric baseline Interval from $BASE_RPT — is it '?'/'-' (unbounded)? Synthesize the baseline with bounded trip counts (compile-time 64x64x64 or #pragma HLS loop_tripcount) so Vitis can report a numeric top-function Interval."
fi
if [ -z "$FINAL_II" ]; then
    if ! looks_like_report "$FINAL_RPT"; then
        fail "$FINAL_RPT is not a Vitis C-synthesis report — pin the REAL csynth report, not a hand-written summary of derived numbers."
    fi
    fail "could not read a numeric optimized Interval from $FINAL_RPT — is it '?'/'-' (unbounded)? Synthesize with bounded trip counts."
fi
[ "$FINAL_II" -gt 0 ] 2>/dev/null || fail "optimized Interval is not a positive integer: '$FINAL_II'"

# throughput speedup = baseline_II / optimized_II ; pass if >= TARGET  (awk float)
RESULT="$(awk -v b="$BASE_II" -v o="$FINAL_II" -v t="$TARGET" \
    'BEGIN { s=b/o; printf "%.3f", s; exit (s+1e-9 >= t ? 0 : 1) }')"
RC=$?
echo "[gate] measured throughput speedup   : ${RESULT}x  (baseline II ${BASE_II} / optimized II ${FINAL_II})"

if [ $RC -eq 0 ]; then
    echo "THROUGHPUT-GATE PASS: measured ${RESULT}x >= ${TARGET}x (from real synth report Interval, independent of results.json)"
    exit 0
fi
fail "measured ${RESULT}x < ${TARGET}x target"
