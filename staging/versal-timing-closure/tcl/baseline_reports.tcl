# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# =============================================================================
# baseline_reports.tcl  --  UG1788 per-stage report bundle for timing closure
# -----------------------------------------------------------------------------
# Generates the standard UG1788 "Timing Baselining" report set for the CURRENT
# in-memory design, regardless of stage (post-opt, post-place, post-phys_opt,
# post-route). Family/device independent: works on any Versal part.
#
# Usage (from a vivado_execute call):
#   source .github/skills/versal-timing-closure/tcl/baseline_reports.tcl
#   vtc_baseline_reports <stage_tag> <out_dir>
# Example:
#   vtc_baseline_reports postplace vivado_agentic_ai_reports/versal-timing-closure
#
# Design names are NEVER hard-coded; everything derives from current_design.
# Compile-time efficient (UG835/UG894): get_* results cached, report_* never
# called twice for the same output.
# =============================================================================

proc vtc_baseline_reports {stage out_dir} {
    if {[catch {current_design} cur]} {
        error "vtc_baseline_reports: no design open"
    }
    file mkdir $out_dir

    # Cache design context once and reuse.
    set part   [get_property PART [current_design]]
    set slrs   [get_slrs]
    set n_slr  [llength $slrs]
    set clks   [get_clocks]
    set state  [get_property DESIGN_MODE [current_design]]
    puts "VTC stage=$stage design=$cur part=$part slrs=$n_slr clocks=[llength $clks]"

    set p "$out_dir/${stage}"

    # 1. QoR Assessment (UG1788 Initial Design Checks / scoring).
    #    -csv_output_dir emits qor_timing_*.csv and qor_dont_touch_*.csv.
    catch {
        report_qor_assessment -file ${p}_qor_assessment.rpt \
            -csv_output_dir ${out_dir}/qor_csv_${stage}
    }

    # 2. QoR Suggestions (automatable fixes). -file writes the human report.
    catch { report_qor_suggestions -file ${p}_qor_suggestions.rpt }

    # 3. Timing summary (WNS/TNS/WHS/THS + failing endpoints).
    catch { report_timing_summary -file ${p}_timing_summary.rpt }

    # 4. Design analysis: setup/hold path characteristics, logic-level
    #    distribution, congestion, and complexity (Rent / avg fanout).
    catch {
        report_design_analysis -setup -logic_level_distribution \
            -of_timing_paths [get_timing_paths -max_paths 50 -setup] \
            -file ${p}_design_analysis_setup.rpt
    }
    catch {
        report_design_analysis -congestion -complexity \
            -file ${p}_design_analysis_cong.rpt
    }

    # 5. Methodology checks (TIMING-*).
    catch { report_methodology -file ${p}_methodology.rpt }

    # 6. Clock interaction + utilization (per-SLR if SSI).
    catch { report_clock_interaction -delay_type min_max -file ${p}_clock_interaction.rpt }
    if {$n_slr > 1} {
        catch { report_utilization -slr -file ${p}_utilization_slr.rpt }
    } else {
        catch { report_utilization -file ${p}_utilization.rpt }
    }

    # 6b. Packing/fanout limiters: control sets (>7.5% guideline) + top high-fanout
    #     nets (reset/CE spreaders). Cheap and high-signal for congestion triage.
    catch { report_control_sets -verbose -file ${p}_control_sets.rpt }
    catch { report_high_fanout_nets -load_types -max_nets 25 -file ${p}_high_fanout.rpt }

    # 7. Route status is only meaningful once routing has run.
    if {$stage eq "postroute" || $stage eq "final"} {
        catch { report_route_status -file ${p}_route_status.rpt }
    }

    # Compact one-line QoR snapshot for the iteration log. report_timing_summary
    # was already written to file above; reuse get_property on timing paths
    # instead of re-running the full report.
    set wns [get_property SLACK [lindex [get_timing_paths -max_paths 1 -setup] 0]]
    set whs [get_property SLACK [lindex [get_timing_paths -max_paths 1 -hold] 0]]
    puts "VTC_QOR stage=$stage WNS=$wns WHS=$whs"
    return "${p}_*.rpt"
}
