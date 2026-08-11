# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# =============================================================================
# overconstrain_flow.tcl  --  Targeted setup over-constraint (OC) P&R lever
# -----------------------------------------------------------------------------
# Closes a small, PERSISTENT setup gap on a SPECIFIC set of inter-clock paths by
# tightening ONLY those paths during place/phys_opt/route, then REMOVING the
# tightening before an HONEST sign-off. This is the lever that closes 0-logic
# structural paths whose setup is limited by route delay + launch/capture clock
# imbalance (e.g. Versal XPHY boundary registers: *_rxclk -> pll_clkoutphy_*_DIV4).
#
# WHY a clock-uncertainty tightening and NOT a timing exception:
#   set_clock_uncertainty -setup adds pessimism, biasing the placer+router to
#   pull the launch FF closer / shorten the route. It is NOT a false_path /
#   clock_groups / max_delay "cheat": it makes the path HARDER, not ignored, and
#   is fully removed before sign-off. The final result is reported with the
#   design's INHERENT uncertainty only (user uncertainty UU = 0).
#
# Usage (source from a vivado_execute call, or run inside an LSF Vivado session):
#   # 1) set the parameters (all optional except FROM/TO patterns), then:
#   source .github/skills/versal-timing-closure/tcl/overconstrain_flow.tcl
#   vtc_overconstrain_flow
#
# Parameters are read from global vars if present, else defaults are used:
#   VTC_OC_FROM_PAT   clock-name pattern(s) for LAUNCH clocks   (e.g. {*_rxclk})
#   VTC_OC_TO_PAT     clock-name pattern(s) for CAPTURE clocks  (e.g. {pll_clkoutphy*})
#   VTC_OC_VALUE      setup over-constraint in ns               (default 0.100)
#   VTC_PLACE_ARGS    place_design args      (default {-directive AggressiveExplore})
#   VTC_PHYSOPT_ARGS  pre-route phys_opt args (default {-directive AggressiveExplore})
#   VTC_ROUTE_ARGS    route_design args      (default {-directive AggressiveExplore})
#   VTC_PR_PHYSOPT_ARGS post-route phys_opt args (default {-directive AggressiveExplore})
#   VTC_RUNDIR        output dir (default vivado_agentic_ai_reports/versal-timing-closure)
#
# Design names are NEVER hard-coded; FROM/TO clocks resolve from get_clocks at
# runtime. Compile-time efficient (UG835/UG894): get_clocks cached once, the
# tightening is applied/removed over cached collections.
# =============================================================================

proc vtc_oc_param {name default} {
    upvar #0 $name g
    if {[info exists g] && $g ne ""} { return $g }
    return $default
}

# Apply (sign=+1) or remove (sign=-1) a targeted setup over-constraint on every
# from-clock -> all-to-clocks pair. Returns the number of from-clocks touched.
proc vtc_oc_apply {from_clks to_clks value sign} {
    set n 0
    foreach r $from_clks {
        if {$sign > 0} {
            if {![catch {set_clock_uncertainty -setup $value -from $r -to $to_clks}]} { incr n }
        } else {
            # Prefer reset_clock_uncertainty; fall back to setting 0 if needed.
            if {[catch {reset_clock_uncertainty -setup -from $r -to $to_clks}]} {
                catch {set_clock_uncertainty -setup 0 -from $r -to $to_clks}
            }
            incr n
        }
    }
    return $n
}

proc vtc_overconstrain_flow {} {
    if {[catch {current_design} cur]} { error "vtc_overconstrain_flow: no design open" }

    set from_pat  [vtc_oc_param VTC_OC_FROM_PAT ""]
    set to_pat    [vtc_oc_param VTC_OC_TO_PAT   ""]
    if {$from_pat eq "" || $to_pat eq ""} {
        error "vtc_overconstrain_flow: set VTC_OC_FROM_PAT and VTC_OC_TO_PAT (the failing clock-pair groups) first"
    }
    set value     [vtc_oc_param VTC_OC_VALUE 0.100]
    set place_a   [vtc_oc_param VTC_PLACE_ARGS      {-directive AggressiveExplore}]
    set physopt_a [vtc_oc_param VTC_PHYSOPT_ARGS    {-directive AggressiveExplore}]
    set route_a   [vtc_oc_param VTC_ROUTE_ARGS      {-directive AggressiveExplore}]
    set pr_phys_a [vtc_oc_param VTC_PR_PHYSOPT_ARGS {-directive AggressiveExplore}]
    set rundir    [vtc_oc_param VTC_RUNDIR vivado_agentic_ai_reports/versal-timing-closure]
    file mkdir $rundir

    # Resolve the failing clock-pair groups from ACTUAL clock names (cached once).
    set from_clks [get_clocks -quiet $from_pat]
    set to_clks   [get_clocks -quiet $to_pat]
    if {[llength $from_clks] == 0 || [llength $to_clks] == 0} {
        error "vtc_overconstrain_flow: no clocks matched FROM='$from_pat' (got [llength $from_clks]) or TO='$to_pat' (got [llength $to_clks])"
    }
    puts "VTC_OC from=[llength $from_clks] clks -> to=[llength $to_clks] clks, OC=$value ns"

    # --- Apply targeted OC (removed before sign-off) ---
    set napplied [vtc_oc_apply $from_clks $to_clks $value 1]
    puts "VTC_OC applied $value ns on $napplied from-clocks"

    # --- Place / pre-route phys_opt (OC active) ---
    eval place_design $place_a
    catch { report_timing_summary -no_detailed_paths -file $rundir/oc_postplace_timing_summary.rpt }
    if {[catch {eval phys_opt_design $physopt_a} e]} { puts "VTC_OC WARN phys_opt: $e" }

    # --- Route / post-route phys_opt (OC active) ---
    eval route_design $route_a
    if {[catch {eval phys_opt_design $pr_phys_a} e]} { puts "VTC_OC WARN pr phys_opt: $e" }

    # --- Remove OC, then HONEST sign-off (inherent uncertainty only) ---
    set nremoved [vtc_oc_apply $from_clks $to_clks $value -1]
    puts "VTC_OC removed on $nremoved from-clocks (sign-off uses inherent uncertainty)"

    set ts [report_timing_summary -file $rundir/oc_signoff_timing_summary.rpt -return_string]
    catch { report_route_status -file $rundir/oc_signoff_route_status.rpt }
    catch { write_checkpoint -force $rundir/oc_signoff_closed.dcp }

    # Compact QoR snapshot for the iteration log (reuse timing paths, no re-report).
    set wns [get_property SLACK [lindex [get_timing_paths -max_paths 1 -setup] 0]]
    set whs [get_property SLACK [lindex [get_timing_paths -max_paths 1 -hold] 0]]
    puts "VTC_OC_SIGNOFF WNS=$wns WHS=$whs (OC removed)"
    return [list wns $wns whs $whs dcp $rundir/oc_signoff_closed.dcp]
}
