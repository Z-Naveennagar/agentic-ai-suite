if {[llength $argv] < 1} {
    error "usage: run_sim.tcl <project.xpr>"
}
set root [file normalize [file dirname [info script]]]
open_project [file normalize [lindex $argv 0]]
set_property top regression_tb [get_filesets sim_1]
update_compile_order -fileset sim_1
launch_simulation -simset sim_1 -mode behavioral
set terminal_pass [get_value -radix unsigned /regression_tb/test_pass]
if {$terminal_pass ne "1"} {
    error "BEHAVIORAL_REGRESSION_FAIL: terminal pass flag is $terminal_pass"
}
set fh [open [file join $root reports simulation_summary.json] w]
puts $fh "{\"behavioral_regression\": \"PASS\", \"terminal_pass_flag\": 1, \"expected_marker\": \"REGRESSION_PASS\"}"
close $fh
close_sim
close_project
