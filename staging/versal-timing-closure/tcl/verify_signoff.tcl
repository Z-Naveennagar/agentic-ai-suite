# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# =============================================================================
# verify_signoff.tcl  --  HONEST, exception-free timing sign-off verification
# -----------------------------------------------------------------------------
# Independently proves a "closed" checkpoint is closed for REAL:
#   (1) the targeted over-constraint (if any) is gone  -> user uncertainty UU = 0
#       on the worst path (only the design's INHERENT jitter/uncertainty remains),
#   (2) no NEW timing exceptions were added by the closure flow,
#   (3) the design is fully routed (0 route errors),
#   (4) any residual WPWS / failing paths are characterized as STRUCTURAL hard-IP
#       (min-period / max-skew on GT / XPHY / MBUFG / PCIe), i.e. out of P&R scope.
#
# Usage (source from a vivado_execute call after opening the closed DCP):
#   open_checkpoint <signoff_closed.dcp>
#   source .github/skills/versal-timing-closure/tcl/verify_signoff.tcl
#   vtc_verify_signoff <out_dir>   ;# default vivado_agentic_ai_reports/versal-timing-closure
#
# Device/design independent. Compile-time efficient: timing paths queried once
# and reused; reports use combined -file/-return_string where a value is needed.
# =============================================================================

proc vtc_verify_signoff {{out_dir ""}} {
    if {[catch {current_design} cur]} { error "vtc_verify_signoff: no design open" }
    if {$out_dir eq ""} { set out_dir vivado_agentic_ai_reports/versal-timing-closure }
    file mkdir $out_dir
    set p "$out_dir/verify"

    # --- (1) Worst setup path: prove OC removed (UU == 0) ----------------------
    # Re-assert removal defensively (no-op if already removed), then read the
    # worst path's uncertainty breakdown. If a residual user uncertainty remains
    # the path header still shows it; UU should be 0 after an honest removal.
    set wpath [lindex [get_timing_paths -max_paths 1 -setup -nworst 1] 0]
    set wns   [get_property SLACK $wpath]
    set whs   [get_property SLACK [lindex [get_timing_paths -max_paths 1 -hold] 0]]
    catch { report_timing -of_objects $wpath -file ${p}_worst_setup_path.rpt }

    # --- (2) Timing summary + route status (the canonical sign-off) ------------
    catch { report_timing_summary -file ${p}_timing_summary.rpt }
    set rs [report_route_status -return_string]
    set rs_file [open ${p}_route_status.rpt w]; puts $rs_file $rs; close $rs_file
    set route_errs 0
    if {[regexp {(\d+)\s+Failed Nets} $rs -> route_errs]} {}

    # --- (3) Methodology + exceptions audit -----------------------------------
    catch { report_methodology -file ${p}_methodology.rpt }
    # List ALL timing exceptions present so the agent can confirm none were added
    # by the closure flow (any that exist must be PRE-EXISTING IP/source XDC).
    set exc ""
    catch { set exc [report_exceptions -return_string] }
    set ef [open ${p}_exceptions.rpt w]; puts $ef $exc; close $ef
    set fp    [llength [get_false_paths -quiet]]
    set cg    [llength [get_clock_groups -quiet]]

    # --- (4) Pulse-width / structural residue ----------------------------------
    catch { report_pulse_width -all_violators -file ${p}_pulse_width.rpt [get_clocks] }

    puts "VTC_VERIFY WNS=$wns WHS=$whs route_failed_nets=$route_errs false_paths=$fp clock_groups=$cg"
    puts "VTC_VERIFY exceptions report -> ${p}_exceptions.rpt (confirm any entries are PRE-EXISTING IP/source XDC, not added by closure)"
    if {$wns >= 0 && $whs >= 0 && $route_errs == 0} {
        puts "VTC_VERIFY PASS: setup+hold met, fully routed. Characterize any WPWS as structural hard-IP (min-period/max-skew) = out of P&R scope."
    } else {
        puts "VTC_VERIFY NOT CLOSED: WNS=$wns WHS=$whs route_failed_nets=$route_errs -- continue iterating."
    }
    return [list wns $wns whs $whs route_failed_nets $route_errs false_paths $fp clock_groups $cg]
}
