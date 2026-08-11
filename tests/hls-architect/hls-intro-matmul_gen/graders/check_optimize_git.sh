#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SOFT process-discipline signal: did /hls-optimize follow its per-attempt git
# commit protocol (SKILL Step 6b + reference/init-component.md)?
#
# The skill mandates: a baseline commit ("Initial commit: baseline HLS kernel")
# plus ONE commit per optimization attempt — including failed attempts — whose
# message carries a Hypothesis/Observed body (or an `experiment(...)` subject).
#
# This reads the pinned `optimize_git_log.txt` (full `git log` the agent copied
# out of the HLS component) and checks:
#   1. >= MIN_COMMITS distinct commits are present (baseline + >= 1 attempt)
#   2. the per-attempt hypothesis/observed bookkeeping appears at least once
#
# Graded SOFT (mandatory: false) — it measures adherence without hard-failing a
# correct run whose bookkeeping differs. Promote to mandatory once proven.
#
#   $1 = minimum commit count (default 2)
#
# Exit 0 -> PASS (score 1.0)   |   Exit non-zero -> FAIL (score 0.0)
# ─────────────────────────────────────────────────────────────────────────────
set -u

WS="${SKILL_TEST_WORKSPACE_DIR:-${WAZA_WORKSPACE_DIR:-$PWD}}"
CASE="hls-intro-matmul_gen_01"
MIN_COMMITS="${1:-2}"
LOG="$WS/outputs/$CASE/optimize_git_log.txt"

fail() { echo "OPTIMIZE-GIT-GATE FAIL: $*"; exit 1; }

[ -f "$LOG" ] || fail "pinned git log missing at $LOG — the agent must copy 'git -C <component> log' here"
[ -s "$LOG" ] || fail "pinned git log at $LOG is empty"

# Count commits. `git log` default format starts each commit with 'commit <sha>';
# fall back to counting `--oneline`-style 7-40 hex-prefixed lines if the agent
# pinned a one-line log instead.
N_COMMITS="$(grep -cE '^commit [0-9a-f]{7,40}' "$LOG")"
if [ "${N_COMMITS:-0}" -eq 0 ] 2>/dev/null; then
    N_COMMITS="$(grep -cE '^[0-9a-f]{7,40} ' "$LOG")"
fi
echo "[gate] commits found     : ${N_COMMITS:-0}"
echo "[gate] commits required  : >= ${MIN_COMMITS}"

[ "${N_COMMITS:-0}" -ge "$MIN_COMMITS" ] 2>/dev/null \
    || fail "only ${N_COMMITS:-0} commit(s) in the log — expected a baseline commit plus >= 1 per-attempt commit (Step 6b)"

# Per-attempt bookkeeping: Hypothesis/Observed body, or an experiment( subject.
if grep -qiE 'hypothesis:|observed:|experiment\(' "$LOG"; then
    echo "[gate] per-attempt bookkeeping tokens (Hypothesis/Observed/experiment): FOUND"
else
    fail "no per-attempt commit bookkeeping (Hypothesis:/Observed:/experiment(...)) found in the git log — Step 6b commit format not followed"
fi

echo "OPTIMIZE-GIT-GATE PASS: ${N_COMMITS} commits with per-attempt bookkeeping present"
exit 0
