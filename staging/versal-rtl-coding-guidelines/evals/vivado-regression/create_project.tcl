set root [file normalize [file dirname [info script]]]
if {[llength $argv] > 0} {
    set work [file normalize [lindex $argv 0]]
} else {
    set work [file join $root work]
}
file mkdir $work
create_project -force versal_skill_regression [file join $work versal_skill_regression] -part xcvc1902-vsva2197-2MP-e-S
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY XPM_CDC} [current_project]
set original_dir [pwd]
cd $root
add_files [list rtl/interfaces.sv rtl/common_blocks.sv rtl/versal_recommendations_top.sv]
add_files -fileset constrs_1 constraints/top.xdc
add_files -fileset sim_1 tb/regression_tb.sv
cd $original_dir
set_property file_type SystemVerilog [get_files *.sv]
set_property top versal_recommendations_top [current_fileset]
set_property top regression_tb [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
set_property strategy Flow_PerfOptimized_high [get_runs synth_1]
list PROJECT [get_property NAME [current_project]] PART [get_property PART [current_project]] TOP [get_property TOP [current_fileset]]
