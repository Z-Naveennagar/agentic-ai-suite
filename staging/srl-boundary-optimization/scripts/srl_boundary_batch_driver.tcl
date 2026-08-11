## srl_boundary_batch_driver.tcl - open a post-opt/pre-place DCP and run the SRL-boundary advisor.
set DCP    [lindex $argv 0]
set OUTDIR [lindex $argv 1]
set HERE   [file dirname [info script]]
open_checkpoint $DCP
source $HERE/detect_srl_boundary.tcl
::srlb::run_srl_boundary_analysis $OUTDIR
puts DONE_SRL_BOUNDARY_RUN
