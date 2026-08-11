## control_set_batch_driver.tcl - open DCP + run the control-set analysis.
set DCP    [lindex $argv 0]
set OUTDIR [lindex $argv 1]
set HERE   [file dirname [info script]]
open_checkpoint $DCP
source $HERE/detect_control_sets.tcl
run_control_set_analysis $OUTDIR
puts DONE_CS_RUN
