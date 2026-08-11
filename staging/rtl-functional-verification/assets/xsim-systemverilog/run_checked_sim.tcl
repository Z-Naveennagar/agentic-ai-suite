# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# Usage: vivado -mode batch -source run_checked_sim.tcl -tclargs <project.xpr> <simset> <tb_top> <pass_signal>
if {[llength $argv] != 4} {
    error "usage: run_checked_sim.tcl <project.xpr> <simset> <tb_top> <pass_signal>"
}
set project_path [file normalize [lindex $argv 0]]
set simset [lindex $argv 1]
set tb_top [lindex $argv 2]
set pass_signal [lindex $argv 3]
set run_error [catch {
    open_project $project_path
    set sim_fileset [get_filesets $simset]
    if {[llength $sim_fileset] != 1} {error "simulation fileset not found: $simset"}
    set_property top $tb_top $sim_fileset
    update_compile_order -fileset $sim_fileset
    launch_simulation -simset $sim_fileset -mode behavioral
    set terminal_pass [get_value -radix unsigned $pass_signal]
    if {$terminal_pass ne "1"} {
        error "BEHAVIORAL_REGRESSION_FAIL: terminal pass flag is $terminal_pass"
    }
    puts "BEHAVIORAL_REGRESSION_PASS top=$tb_top"
} run_message run_options]
catch {close_sim}
catch {close_project}
if {$run_error} {return -options $run_options $run_message}
