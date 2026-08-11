## bram_uram_batch_driver.tcl - open DCP + run the BRAM/URAM output-reg detector.
set DCP    [lindex $argv 0]
set OUTDIR [lindex $argv 1]
set HERE   [file dirname [info script]]
open_checkpoint $DCP
source $HERE/detect_bram_uram_oreg.tcl
run_bram_uram_oreg $OUTDIR
puts DONE_BUR_RUN
