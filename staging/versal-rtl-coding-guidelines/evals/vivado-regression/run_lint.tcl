if {[llength $argv] < 1} {
    error "usage: run_lint.tcl <project.xpr>"
}
open_project [file normalize [lindex $argv 0]]
synth_design -top versal_recommendations_top -part xcvc1902-vsva2197-2MP-e-S -lint
close_project
