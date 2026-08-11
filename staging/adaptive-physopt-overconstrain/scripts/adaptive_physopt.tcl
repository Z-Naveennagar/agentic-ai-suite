#############################################################################
## adaptive_physopt.tcl
##
## Adaptive post-place OVER-CONSTRAIN + multi-pass AggressiveExplore phys_opt.
## Implements the "adaptive-physopt-overconstrain" skill (see SKILL.md).
##
## Selectively over-constrains ONLY the clocks that have setup violations
## (via set_clock_uncertainty), runs sequential phys_opt_design
## -directive AggressiveExplore passes, scores each candidate, stops on
## convergence, then strips the temporary uncertainty for clean signoff.
##
## Usage (batch):
##   vivado -mode batch -source adaptive_physopt.tcl \
##          -tclargs -dcp <post_place.dcp> -mode balanced -max_iter 6
##
## Args:
##   -dcp <path>        required   post-place checkpoint
##   -mode <m>          optional   conservative|balanced|aggressive (def balanced)
##   -clocks {c1 c2}    optional   explicit clocks; default = auto-detect violating
##   -max_iter <N>      optional   max AggressiveExplore passes (default 6)
##   -out_dir <dir>     optional   output directory (default ./physopt_run)
#############################################################################

# -------------------------- arg parsing ----------------------------------
set DCP ""
set MODE balanced
set CLOCKS ""
set MAX_ITER 6
set OUT_DIR "./physopt_run"
for {set i 0} {$i < [llength $argv]} {incr i} {
    set a [lindex $argv $i]
    switch -- $a {
        -dcp      { set DCP      [lindex $argv [incr i]] }
        -mode     { set MODE     [lindex $argv [incr i]] }
        -clocks   { set CLOCKS   [lindex $argv [incr i]] }
        -max_iter { set MAX_ITER [lindex $argv [incr i]] }
        -out_dir  { set OUT_DIR  [lindex $argv [incr i]] }
        default   { puts "WARN: unknown arg '$a'" }
    }
}
if {$DCP eq ""} {
    error "usage: -dcp <post_place.dcp> \[-mode conservative|balanced|aggressive\] \[-clocks {c1 c2}\] \[-max_iter N\] \[-out_dir dir\]"
}
file mkdir $OUT_DIR

# -------------------------- config ---------------------------------------
array set UNC_PCT {conservative 0.02 balanced 0.05 aggressive 0.09}
if {![info exists UNC_PCT($MODE)]} {
    puts "WARN: unknown mode '$MODE', defaulting to balanced"
    set MODE balanced
}
set OC_PCT        $UNC_PCT($MODE)
set OC_CAP_PCT    0.10     ;# never tighten more than 10% of period
set CONG_HIGH     5        ;# report_design_analysis congestion level >=5 is "high"
set REF_WNS_PS    20.0     ;# continue refinement if dWNS improvement > 20ps
set REF_TNS_PCT   5.0      ;#   ...or dTNS improvement > 5%
set STOP_WNS_PS   5.0      ;# terminate when dWNS < 5ps AND
set STOP_TNS_PCT  1.0      ;#                dTNS < 1%
set BUF_GROWTH_PCT 2.0     ;# cell-count growth over this => buffering penalty
set t0 [clock seconds]

# -------------------------- logging --------------------------------------
set LOG {}
proc log {msg} {
    global LOG
    set line "\[[clock format [clock seconds] -format %H:%M:%S]\] $msg"
    puts $line
    lappend LOG $line
}

# -------------------------- helpers --------------------------------------
# Parse WNS / TNS / failing-endpoints (setup) from a report_timing_summary file.
proc parse_timing_summary {file} {
    set wns 0.0 ; set tns 0.0 ; set fep 0
    if {![file exists $file]} { return [list $wns $tns $fep] }
    set fh [open $file r]
    set data [read $fh]
    close $fh
    if {[regexp {Design Timing Summary(.*)} $data -> tail]} {
        foreach line [split $tail "\n"] {
            set t [string trim $line]
            if {$t eq ""} { continue }
            # first numeric row: WNS  TNS  TNS-Failing-Endpoints  TNS-Total-Endpoints ...
            if {[regexp {^(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)} $t -> w tn f tot]} {
                set wns $w ; set tns $tn ; set fep $f
                break
            }
        }
    }
    return [list $wns $tns $fep]
}

# Worst setup slack captured by a single clock (cheap: 1 worst path).
proc clock_wns {clk} {
    set p [get_timing_paths -setup -max_paths 1 -nworst 1 -to $clk -quiet]
    if {[llength $p] == 0} { return 1e30 }
    return [get_property SLACK [lindex $p 0]]
}

# Maximum congestion level (0-7) parsed from a report_design_analysis -congestion file.
proc max_congestion {rptfile} {
    set maxlvl -1
    if {![file exists $rptfile]} { return $maxlvl }
    set fh [open $rptfile r]
    while {[gets $fh line] >= 0} {
        if {[regexp -nocase {north|south|east|west|horizontal|vertical} $line]} {
            foreach tok [regexp -all -inline {\d+} $line] {
                if {$tok <= 7 && $tok > $maxlvl} { set maxlvl $tok }
            }
        }
    }
    close $fh
    return $maxlvl
}

proc cell_count {} { return [llength [get_cells -hier -quiet]] }

proc pctimp {new base} {
    if {$base == 0} { return 0.0 }
    return [expr {double($new - $base) / abs(double($base)) * 100.0}]
}

# =========================================================================
# PHASE 1 : baseline characterization
# =========================================================================
log "PHASE 1: opening checkpoint $DCP"
open_checkpoint $DCP
report_timing_summary -file $OUT_DIR/baseline_timing.rpt -quiet
lassign [parse_timing_summary $OUT_DIR/baseline_timing.rpt] BWNS BTNS BFEP
catch {report_design_analysis -congestion -file $OUT_DIR/baseline_cong.rpt}
set BCONG  [max_congestion $OUT_DIR/baseline_cong.rpt]
set BCELLS [cell_count]
log [format "BASELINE  WNS=%.3fns  TNS=%.3fns  failing_eps=%d  congestion=%d  cells=%d" \
        $BWNS $BTNS $BFEP $BCONG $BCELLS]

# ---- identify violating clocks (auto unless -clocks given) --------------
set violating {}
if {$CLOCKS ne ""} {
    foreach c $CLOCKS {
        if {[llength [get_clocks -quiet $c]]} {
            lappend violating $c
        } else {
            log "WARN: clock '$c' not found, skipping"
        }
    }
    log "using user-specified clocks: $violating"
} else {
    foreach clk [get_clocks -quiet] {
        set cn   [get_property NAME $clk]
        set cwns [clock_wns $clk]
        if {$cwns < 0} {
            lappend violating $cn
            log [format "  violating clock %-28s WNS=%.3fns" $cn $cwns]
        }
    }
    log "auto-detected violating clocks: [expr {[llength $violating] ? $violating : {none}}]"
}

# =========================================================================
# guardrail : high baseline congestion
# =========================================================================
set APPLY_OC 1
if {$BCONG >= $CONG_HIGH} {
    log "GUARDRAIL: baseline congestion $BCONG >= $CONG_HIGH (HIGH) -> NO over-constraining; single phys_opt pass only"
    set APPLY_OC 0
    set MAX_ITER 1
}
if {[llength $violating] == 0} {
    log "no setup-violating clocks detected -> skipping over-constraining"
    set APPLY_OC 0
}

# =========================================================================
# PHASE 2 : selective dynamic over-constraining (violating clocks only)
# =========================================================================
set applied {}
if {$APPLY_OC} {
    log "PHASE 2: applying setup uncertainty ([format %.1f [expr {$OC_PCT*100}]]% of period, mode=$MODE) to violating clocks only"
    foreach cn $violating {
        set clk [get_clocks -quiet $cn]
        if {[llength $clk] == 0} { continue }
        set per [get_property PERIOD $clk]
        if {$per eq "" || $per <= 0} {
            log "  WARN: clock $cn has no PERIOD, skipping"
            continue
        }
        set unc [expr {$OC_PCT * $per}]
        set cap [expr {$OC_CAP_PCT * $per}]
        if {$unc > $cap} { set unc $cap }
        set_clock_uncertainty -setup $unc $clk
        lappend applied $cn
        log [format "  set_clock_uncertainty -setup %.4f (%.1f%%) on %s (period=%.3f)" \
                $unc [expr {$unc/$per*100}] $cn $per]
    }
} else {
    log "PHASE 2: skipped (no over-constraining)"
}

# =========================================================================
# PHASE 3 + 5 : multi-pass AggressiveExplore with convergence refinement
# =========================================================================
set candidates {}
set prev_wns $BWNS
set prev_tns $BTNS
set best_score -1e30
set best_iter 0
set best_dcp ""

log "PHASE 3: up to $MAX_ITER AggressiveExplore pass(es)"
for {set n 1} {$n <= $MAX_ITER} {incr n} {
    log "  --- iteration $n : phys_opt_design -directive AggressiveExplore ---"
    set ts [clock seconds]
    if {[catch {phys_opt_design -directive AggressiveExplore} pe]} {
        log "  phys_opt_design error: $pe -- stopping loop"
        break
    }
    set rt [expr {[clock seconds] - $ts}]

    set dcp $OUT_DIR/iteration_${n}.dcp
    write_checkpoint -force $dcp
    report_timing_summary -file $OUT_DIR/iteration_${n}_timing.rpt -quiet
    lassign [parse_timing_summary $OUT_DIR/iteration_${n}_timing.rpt] wns tns fep
    catch {report_design_analysis -congestion -file $OUT_DIR/iteration_${n}_cong.rpt}
    set cong  [max_congestion $OUT_DIR/iteration_${n}_cong.rpt]
    set cells [cell_count]

    # improvements vs baseline
    set wns_impr_ps  [expr {($wns - $BWNS) * 1000.0}]
    set tns_impr_pct [pctimp $tns $BTNS]
    set ep_red       [expr {$BFEP - $fep}]
    set ep_red_pct   [expr {$BFEP > 0 ? double($ep_red)/$BFEP*100.0 : 0.0}]
    set score        [expr {0.5*$wns_impr_ps + 0.3*$tns_impr_pct + 0.2*$ep_red_pct}]

    # penalties: congestion increase, excessive buffering (cell growth)
    set pen 0.0
    if {$cong > $BCONG && $BCONG >= 0} {
        set pen [expr {$pen + ($cong - $BCONG) * 5.0}]
    }
    set growth [pctimp $cells $BCELLS]
    if {$growth > $BUF_GROWTH_PCT} {
        set pen [expr {$pen + ($growth - $BUF_GROWTH_PCT)}]
    }
    set score [expr {$score - $pen}]

    log [format "  iter %d: WNS=%.3f (%+.1fps)  TNS=%.3f (%+.1f%%)  eps=%d(%+d)  cong=%d  cells=%d(%+.1f%%)  rt=%ds  score=%.2f (pen=%.2f)" \
            $n $wns $wns_impr_ps $tns $tns_impr_pct $fep [expr {-$ep_red}] $cong $cells $growth $rt $score $pen]

    lappend candidates [list $n $wns $tns $fep $cong $cells $rt $score $dcp]
    if {$score > $best_score} {
        set best_score $score ; set best_iter $n ; set best_dcp $dcp
    }

    # ---- convergence: delta vs previous iteration/baseline ----
    set dwns_ps  [expr {($wns - $prev_wns) * 1000.0}]
    set dtns_pct [pctimp $tns $prev_tns]
    log [format "  delta vs prev: dWNS=%+.1fps  dTNS=%+.1f%%" $dwns_ps $dtns_pct]

    if {$APPLY_OC == 0 && $MAX_ITER == 1} {
        log "  single-pass mode (high congestion) -> stop"
        break
    }
    if {$cong >= $CONG_HIGH && $cong > $BCONG && $BCONG >= 0} {
        log "  GUARDRAIL: congestion rose to $cong (>=HIGH) -> stop iterating"
        set prev_wns $wns ; set prev_tns $tns
        break
    }
    if {$dwns_ps < $STOP_WNS_PS && $dtns_pct < $STOP_TNS_PCT} {
        log "  CONVERGED: dWNS<${STOP_WNS_PS}ps AND dTNS<${STOP_TNS_PCT}% -> stop"
        set prev_wns $wns ; set prev_tns $tns
        break
    }
    if {!($dwns_ps > $REF_WNS_PS || $dtns_pct > $REF_TNS_PCT)} {
        log "  improvement below refinement thresholds (>${REF_WNS_PS}ps or >${REF_TNS_PCT}%) -> stop"
        set prev_wns $wns ; set prev_tns $tns
        break
    }
    set prev_wns $wns
    set prev_tns $tns
}

# =========================================================================
# PHASE 4 : select best candidate, remove over-constraint, signoff
# =========================================================================
if {[llength $candidates] == 0} {
    log "PHASE 4: no phys_opt candidates produced -- nothing to select"
} else {
    log [format "PHASE 4: best candidate = iteration %d (score %.2f)" $best_iter $best_score]

    # reopen the best candidate clean, strip temporary uncertainty for signoff
    catch {close_design}
    open_checkpoint $best_dcp
    if {[llength $applied]} {
        foreach cn $applied {
            set clk [get_clocks -quiet $cn]
            if {[llength $clk]} { set_clock_uncertainty -setup 0.0 $clk }
        }
        log "removed temporary setup uncertainty on: $applied"
    }
    report_timing_summary -file $OUT_DIR/best_signoff_timing.rpt -quiet
    lassign [parse_timing_summary $OUT_DIR/best_signoff_timing.rpt] FWNS FTNS FFEP
    write_checkpoint -force $OUT_DIR/best.dcp
    log [format "SIGNOFF (best, uncertainty removed)  WNS=%.3fns  TNS=%.3fns  failing_eps=%d" $FWNS $FTNS $FFEP]
}

# =========================================================================
# outputs : comparison table + summary
# =========================================================================
set C [open $OUT_DIR/physopt_comparison.rpt w]
puts $C [format "%-7s %-10s %-12s %-9s %-6s %-11s %-7s %-8s" \
        "ITER" "WNS(ns)" "TNS(ns)" "FAIL_EP" "CONG" "CELLS" "RT(s)" "SCORE"]
puts $C [format "%-7s %-10.3f %-12.3f %-9d %-6d %-11d %-7s %-8s" \
        "base" $BWNS $BTNS $BFEP $BCONG $BCELLS "-" "-"]
foreach rec $candidates {
    lassign $rec n wns tns fep cong cells rt score
    set tag [expr {$n == $best_iter ? "*" : ""}]
    puts $C [format "%-6s%-1s %-10.3f %-12.3f %-9d %-6d %-11d %-7d %-8.2f" \
            $n $tag $wns $tns $fep $cong $cells $rt $score]
}
close $C

set S [open $OUT_DIR/physopt_summary.txt w]
puts $S "================ ADAPTIVE POST-PLACE PHYSOPT SUMMARY ================"
puts $S "checkpoint          : $DCP"
puts $S "mode                : $MODE  (setup uncertainty [format %.1f [expr {$OC_PCT*100}]]% of period, cap [format %.0f [expr {$OC_CAP_PCT*100}]]%)"
puts $S "over-constrained    : [expr {[llength $applied] ? $applied : {none}}]"
puts $S "baseline            : WNS=[format %.3f $BWNS]ns  TNS=[format %.3f $BTNS]ns  fail_eps=$BFEP  cong=$BCONG"
if {[llength $candidates]} {
    puts $S "best candidate      : iteration $best_iter (score [format %.2f $best_score]) -> $OUT_DIR/best.dcp"
    if {[info exists FWNS]} {
        puts $S "signoff (best)      : WNS=[format %.3f $FWNS]ns  TNS=[format %.3f $FTNS]ns  fail_eps=$FFEP"
    }
    puts $S "recommended directive sequence:"
    for {set k 1} {$k <= $best_iter} {incr k} {
        puts $S "   pass $k : phys_opt_design -directive AggressiveExplore"
    }
} else {
    puts $S "best candidate      : none"
}
puts $S "--------------------------------------------------------------------"
puts $S "decisions log:"
foreach l $LOG { puts $S "  $l" }
puts $S "--------------------------------------------------------------------"
puts $S "elapsed             : [expr {[clock seconds]-$t0}] s"
close $S

log "WROTE $OUT_DIR/physopt_comparison.rpt , $OUT_DIR/physopt_summary.txt , $OUT_DIR/best.dcp"
log "DONE_ADAPTIVE_PHYSOPT in [expr {[clock seconds]-$t0}] s"
