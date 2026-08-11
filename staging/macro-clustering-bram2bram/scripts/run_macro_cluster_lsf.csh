#!/bin/csh -f
###########################################################################
## run_macro_cluster_lsf.csh <dcp> <outdir>
## LSF wrapper: open a placed+routed DCP on a RHEL8 compute node and run the
## BRAM/URAM macro-cluster (mem -> N*LUT -> mem) detector in batch.
##
## Submit from the login node:
##   bsub -q long -J bram2bram -n 2 \
##        -R "select[ostype==rhelws810 || ostype==rhelws86 || ostype==rhelws89 || ostype==rhelws87] rusage[mem=65536]" \
##        -o <outdir>/bram2bram.%J.log \
##        ./run_macro_cluster_lsf.csh <dcp> <outdir>
## Env tunables (LSF forwards them): MIN_LEVELS MAX_LEVELS SLACK_MAX MIN_DIST
##   PATTERNS SAME_PARTITION (see detect_macro_clusters.tcl).
###########################################################################
if ( $#argv < 2 ) then
    echo "usage: run_macro_cluster_lsf.csh <dcp> <outdir>"
    exit 1
endif
set DCP    = $argv[1]
set OUTDIR = $argv[2]
set HERE = `dirname $0`
cd $HERE
set HERE = `pwd`
set VIVADO = /proj/primebuilds/2026.1_PRIME_daily_latest/installs/lin64/2026.1/Vivado/bin/vivado
mkdir -p $OUTDIR
cd $OUTDIR
$VIVADO -mode batch -notrace -log $OUTDIR/bram2bram_vivado.log \
    -source $HERE/macro_cluster_batch_driver.tcl -tclargs $DCP $OUTDIR
