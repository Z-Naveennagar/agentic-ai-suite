if {[llength $argv] < 1} {
    error "usage: run_synth.tcl <project.xpr>"
}
set script_root [file normalize [file dirname [info script]]]
open_project [file normalize [lindex $argv 0]]
synth_design -top versal_recommendations_top -part xcvc1902-vsva2197-2MP-e-S
source [file join $script_root check_synth.tcl]
close_project
