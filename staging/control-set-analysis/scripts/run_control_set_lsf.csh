#!/bin/csh -f
###########################################################################
## run_control_set_lsf.csh <dcp> <outdir>
## LSF wrapper: open a DCP on a RHEL8 compute node and run the control-set
## fragmentation analysis in batch.
##
## Submit from the login node:
##   bsub -q long -J cset -R "select[type=X86_64 && osdistro=rhel && osver=ws8] \
##        rusage[mem=60000]" -o <outdir>/cset.%J.log \
##        ./run_control_set_lsf.csh <dcp> <outdir>
## Env: DEPTH (module hierarchy depth, default 8), MIN_FF (default 200).
###########################################################################
if ( $#argv < 2 ) then
    echo "usage: run_control_set_lsf.csh <dcp> <outdir>"
    exit 1
endif
set DCP = $argv[1]
set OUTDIR = $argv[2]
set HERE = `dirname $0`
cd $HERE
set HERE = `pwd`
set VIVADO = /proj/primebuilds/2026.1_PRIME_daily_latest/installs/lin64/2026.1/Vivado/bin/vivado
mkdir -p $OUTDIR
cd $OUTDIR
$VIVADO -mode batch -notrace -log $OUTDIR/cset_vivado.log \
    -source $HERE/control_set_batch_driver.tcl -tclargs $DCP $OUTDIR
