#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# hls-optimize SKILL-CONFORMANCE gate for the hls-intro-matmul_gen suite.
#
# Purpose: prove the hls-optimize skill actually FOLLOWED ITS OWN DESIGNED
# WORKFLOW, not just that the final numbers look good. It emits a per-step
# PASS / VIOLATION / N-A report and HARD-FAILS (exit non-zero) on any violation.
#
# The rules come straight from hls-optimize/SKILL.md:
#   * Inner loop      — csim + csynth run (baseline_synth.rpt + final_synth.rpt).
#   * Step 0a baseline — baseline is meant to have cosim+impl too (reported;
#                        folded into the cosim/impl evidence below).
#   * Step 7 escalation — "Latency improved >= 10% OR II reduced on a dominant
#                        loop -> run cosim." PER-ATTEMPT (read from
#                        qor_history.csv). If escalation was due, cosim MUST have
#                        run. (HARD)
#   * impl gating      — "run impl ... only when cosim confirms improvement." So
#                        once cosim has run, impl is expected too. (HARD, but
#                        only evaluated when cosim actually ran.)
#
# Evidence (program graders see the workspace + the agent's final stdout on
# stdin, NOT the full command transcript), so execution is inferred from:
#   cosim ran  <- pinned cosim.rpt (valid) OR a real ".../hls/sim" cosim output
#                 dir OR results.json has cosim_interval_cycles OR stdout says so
#   impl ran   <- a real ".../hls/impl/{ip,verilog,vhdl}" export dir (unified
#                 component flow) OR ".../hls/impl/report" (classic solution
#                 flow) OR results.json has a post-route/impl key
#
#   $1 = escalation threshold percent (default 10, matching the skill's ">=10%")
#
# Exit 0 -> CONFORMANT (score 1.0)  |  Exit non-zero -> NON-CONFORMANT (0.0)
# ─────────────────────────────────────────────────────────────────────────────
set -u

WS="${SKILL_TEST_WORKSPACE_DIR:-${WAZA_WORKSPACE_DIR:-$PWD}}"
CASE="hls-intro-matmul_gen_01"
THRESH="${1:-10}"

OUT_DIR="$WS/outputs/$CASE"
QOR="$OUT_DIR/qor_history.csv"
BASE_RPT="$OUT_DIR/baseline_synth.rpt"
FINAL_RPT="$OUT_DIR/final_synth.rpt"
COSIM_RPT="$OUT_DIR/cosim.rpt"
RESULTS="$OUT_DIR/results.json"

STDIN_TXT="$(cat 2>/dev/null || true)"   # agent's final stdout summary

VIOLATIONS=0
report() { printf '  [%-9s] %-22s %s\n' "$1" "$2" "$3"; }
violation() { VIOLATIONS=$((VIOLATIONS+1)); report "VIOLATION" "$1" "$2"; }
ok()  { report "PASS" "$1" "$2"; }
na()  { report "N-A" "$1" "$2"; }

echo "════════ hls-optimize SKILL-CONFORMANCE REPORT ════════"

# ── extract a column from a csynth Performance-Estimates summary table ───────
#   f[3]=Latency(cyc) max   f[7]=Interval/II max
extract_col() {
    awk -v col="$2" '
        /== Performance Estimates/ { perf=1 }
        perf && /\+ Latency:/      { lat=1 }
        lat  && /\* Summary:/      { summ=1; next }
        summ && /\+ Detail:/       { exit }
        summ && /^[[:space:]]*\|/ {
            line=$0; gsub(/[[:space:]]/,"",line)
            n=split(line, f, "|"); if (f[2] ~ /^[0-9]+$/) { print f[col]; exit }
        }' "$1"
}

# ── STEP 1: inner loop (csim + csynth) ───────────────────────────────────────
if [ -f "$FINAL_RPT" ] && grep -qi interval "$FINAL_RPT" 2>/dev/null; then
    ok "inner-loop csynth" "final_synth.rpt present and valid"
else
    violation "inner-loop csynth" "final_synth.rpt missing/invalid — csynth inner loop not evidenced"
fi

# ── Determine whether Step 7 escalation was DUE ──────────────────────────────
DUE=""; ESC_SRC=""
if [ -f "$QOR" ]; then
    Q="$(awk -F, -v t="$THRESH" '
        NR==1 { for(i=1;i<=NF;i++){h=$i; gsub(/[[:space:]"]/,"",h);
                if(h=="lat_max_cyc")lc=i; if(h=="interval")ic=i} next }
        { rows++; lat=$lc+0; iv=$ic+0
          if(rows>1){ if(plat>0){li=(plat-lat)/plat*100; if(li+1e-9>=t)due=1; if(li>ml)ml=li}
                      if(piv>0){ii=(piv-iv)/piv*100;   if(ii+1e-9>=t)due=1; if(ii>mi)mi=ii} }
          plat=lat; piv=iv }
        END { if(lc==0||ic==0){print "nocols";exit} if(rows<2){print "insufficient";exit}
              printf "%s %.2f %.2f", (due?"yes":"no"), ml, mi }' "$QOR")"
    set -- $Q
    case "${1:-}" in
        yes) DUE="yes"; ESC_SRC="qor_history.csv per-attempt (max latency step ${2}%, max II step ${3}%)";;
        no)  DUE="no";  ESC_SRC="qor_history.csv per-attempt (max latency step ${2}%, max II step ${3}%)";;
    esac
fi
if [ -z "$DUE" ] && [ -f "$BASE_RPT" ] && [ -f "$FINAL_RPT" ]; then
    BL=$(extract_col "$BASE_RPT" 3); OL=$(extract_col "$FINAL_RPT" 3)
    BI=$(extract_col "$BASE_RPT" 7); OI=$(extract_col "$FINAL_RPT" 7)
    R="$(awk -v bl="$BL" -v ol="$OL" -v bi="$BI" -v oi="$OI" -v t="$THRESH" '
        function p(b,o){return (b==""||o==""||b+0<=0)?-1:(b-o)/b*100}
        BEGIN{li=p(bl,ol);ii=p(bi,oi);printf "%s %.2f %.2f",(((li+1e-9>=t)||(ii+1e-9>=t))?"yes":"no"),li,ii}')"
    set -- $R
    DUE="$1"; ESC_SRC="baseline-vs-final csynth reports end-to-end (latency ${2}%, II ${3}%) — qor_history.csv unavailable"
fi
[ -z "$DUE" ] && DUE="unknown"

# ── Detect whether cosim actually RAN ────────────────────────────────────────
COSIM_RAN="no"; COSIM_EV=""
if [ -f "$COSIM_RPT" ] && grep -qiE 'co-?sim|c/rtl|rtl' "$COSIM_RPT" 2>/dev/null \
        && grep -qiE 'latency' "$COSIM_RPT" 2>/dev/null && grep -qE '[0-9]{2,}' "$COSIM_RPT" 2>/dev/null; then
    COSIM_RAN="yes"; COSIM_EV="pinned cosim.rpt"
elif find "$WS" -type d -path '*/hls/sim' 2>/dev/null | grep -q .; then
    COSIM_RAN="yes"; COSIM_EV="hls/sim cosim output dir"
elif [ -f "$RESULTS" ] && grep -qiE '"cosim_[a-z_]*(cycles|latency|interval)"' "$RESULTS" 2>/dev/null; then
    COSIM_RAN="yes"; COSIM_EV="results.json cosim_* key"
elif printf '%s' "$STDIN_TXT" | grep -qiE 'co-?sim(ulation)?.*(ran|pass|latency|confirm|cycles)'; then
    COSIM_RAN="yes"; COSIM_EV="agent stdout reports cosim"
fi

# ── STEP 7: cosim escalation conformance (HARD) ──────────────────────────────
if [ "$DUE" = "yes" ]; then
    if [ "$COSIM_RAN" = "yes" ]; then
        ok "Step7 cosim" "escalation due [${ESC_SRC}] and cosim ran (${COSIM_EV})"
    else
        violation "Step7 cosim" "escalation DUE [${ESC_SRC}] but NO evidence cosim ran — skill stopped at the csynth estimate instead of escalating (SKILL.md Step 7)"
    fi
elif [ "$DUE" = "no" ]; then
    na "Step7 cosim" "no attempt crossed ${THRESH}% — escalation not required"
else
    na "Step7 cosim" "escalation could not be determined (no qor_history.csv or reports)"
fi

# ── impl gating conformance (HARD, only once cosim has run) ───────────────────
IMPL_RAN="no"; IMPL_EV=""
# The unified component flow (v++/vitis-run --mode hls) exports/packages impl to
# hls/impl/{ip,verilog,vhdl,misc}; the older solution-based project flow writes
# hls/impl/report. Accept EITHER layout — the impl/export step ran in both cases.
if IMPL_DIR=$(find "$WS" -type d \( -path '*/hls/impl/report' -o -path '*/hls/impl/ip' -o -path '*/hls/impl/verilog' -o -path '*/hls/impl/vhdl' \) 2>/dev/null | head -1) && [ -n "$IMPL_DIR" ]; then
    IMPL_RAN="yes"; IMPL_EV="${IMPL_DIR##*/hls/}"
elif [ -f "$RESULTS" ] && grep -qiE '"(post_?route|impl_[a-z_]*|placeRoute)[a-z_]*"' "$RESULTS" 2>/dev/null; then
    IMPL_RAN="yes"; IMPL_EV="results.json impl/post-route key"
fi
if [ "$COSIM_RAN" = "yes" ]; then
    if [ "$IMPL_RAN" = "yes" ]; then
        ok "impl gating" "cosim ran and impl ran (${IMPL_EV})"
    else
        violation "impl gating" "cosim ran but NO evidence impl ran — SKILL.md says run impl once cosim confirms improvement"
    fi
else
    na "impl gating" "cosim did not run, so impl stage is not expected yet"
fi

# ── Step 0a baseline note (informational — the skill's Philosophy tension means
#    this is reported, not independently hard-failed) ─────────────────────────
if [ "$COSIM_RAN" = "no" ]; then
    report "NOTE" "Step0a baseline" "no cosim anywhere => the baseline was NOT taken through cosim+impl either (SKILL.md Step 0a)"
fi

echo "───────────────────────────────────────────────────────"
if [ "$VIOLATIONS" -gt 0 ]; then
    echo "SKILL-CONFORMANCE: NON-CONFORMANT — ${VIOLATIONS} violation(s). The hls-optimize skill did not follow its designed workflow."
    exit 1
fi
echo "SKILL-CONFORMANCE: CONFORMANT — the hls-optimize skill followed its designed workflow."
exit 0
