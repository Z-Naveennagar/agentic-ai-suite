## macro_cluster_batch_driver.tcl - open DCP + run the BRAM/URAM macro-cluster analysis.
set DCP    [lindex $argv 0]
set OUTDIR [lindex $argv 1]
set HERE   [file dirname [info script]]
open_checkpoint $DCP
source $HERE/detect_macro_clusters.tcl
run_macro_cluster_analysis $OUTDIR
puts DONE_MACRO_CLUSTER_RUN
