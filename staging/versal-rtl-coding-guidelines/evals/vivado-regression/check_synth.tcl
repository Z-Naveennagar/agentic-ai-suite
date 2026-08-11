set root [file normalize [file dirname [info script]]]
set report_dir [file join $root reports]
file mkdir $report_dir
set bram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == BRAM}]
set uram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == URAM}]
set dsp [get_cells -hier -filter {REF_NAME == DSP_ALUREG}]
set latches [get_cells -hier -filter {PRIMITIVE_GROUP == REGISTER && PRIMITIVE_SUBGROUP == LATCH}]
set async_regs [get_cells -hier -filter {ASYNC_REG == TRUE}]
set preserved [get_cells -hier -filter {DONT_TOUCH == TRUE}]
report_utilization -file [file join $report_dir utilization.rpt]
report_control_sets -file [file join $report_dir control_sets.rpt]
report_clock_networks -file [file join $report_dir clock_networks.rpt]
report_high_fanout_nets -file [file join $report_dir high_fanout.rpt]
report_design_analysis -logic_level_distribution -file [file join $report_dir logic_levels.rpt]
report_cdc -details -file [file join $report_dir cdc.rpt]
report_exceptions -coverage -file [file join $report_dir exceptions_coverage.rpt]
report_methodology -file [file join $report_dir methodology.rpt]
report_timing_summary -file [file join $report_dir timing_summary.rpt]
set failures {}
set report_failures {}
foreach report_name {utilization.rpt control_sets.rpt clock_networks.rpt high_fanout.rpt logic_levels.rpt cdc.rpt exceptions_coverage.rpt methodology.rpt timing_summary.rpt} {
    set report_path [file join $report_dir $report_name]
    if {![file exists $report_path] || [file size $report_path] == 0} {
        lappend report_failures "$report_name is missing or empty"
        continue
    }
    set report_fh [open $report_path r]
    set report_text [read $report_fh]
    close $report_fh
    if {[regexp -nocase {(^|\n)[^\n]*(CRITICAL WARNING|ERROR:)} $report_text]} {
        lappend report_failures "$report_name contains ERROR or CRITICAL WARNING"
    }
}
if {[llength $bram] < 1} {lappend failures "BRAM not inferred"}
if {[llength $uram] < 1} {lappend failures "URAM not inferred"}
if {[llength $dsp] < 2} {lappend failures "expected DSP58 arithmetic not inferred"}
if {[llength $latches] != 0} {lappend failures "unintended latch inferred"}
if {[llength $async_regs] < 4} {lappend failures "synchronizer registers missing"}
if {[llength $preserved] < 3} {lappend failures "TMR preservation evidence missing"}
foreach report_failure $report_failures {lappend failures $report_failure}
set fh [open [file join $report_dir summary.json] w]
puts $fh "{"
puts $fh "  \"part\": \"[get_property PART [current_project]]\","
puts $fh "  \"bram\": [llength $bram],"
puts $fh "  \"uram\": [llength $uram],"
puts $fh "  \"dsp\": [llength $dsp],"
puts $fh "  \"latches\": [llength $latches],"
puts $fh "  \"async_regs\": [llength $async_regs],"
puts $fh "  \"dont_touch_cells\": [llength $preserved],"
puts $fh "  \"reports_present\": [expr {[llength $report_failures] == 0 ? "true" : "false"}],"
puts $fh "  \"report_error_or_critical\": [expr {[llength $report_failures] == 0 ? "false" : "true"}],"
puts $fh "  \"structural_gate\": \"[expr {[llength $failures] == 0 ? "PASS" : "FAIL"}]\","
puts $fh "  \"failures\": \"[join $failures {; }]\""
puts $fh "}"
close $fh
if {[llength $failures]} {error "STRUCTURAL_GATE_FAIL: [join $failures {; }]"}
list STRUCTURAL_GATE PASS BRAM [llength $bram] URAM [llength $uram] DSP [llength $dsp] LATCH [llength $latches] ASYNC_REG [llength $async_regs] DONT_TOUCH [llength $preserved]
