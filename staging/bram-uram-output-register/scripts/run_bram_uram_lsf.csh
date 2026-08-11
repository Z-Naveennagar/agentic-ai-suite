#!/bin/csh -f
###########################################################################
## run_bram_uram_lsf.csh <dcp> <outdir>
## LSF wrapper: open a DCP on a RHEL8 compute node and run the BRAM/URAM
## output-register timing detector in batch.
##
## Submit from the login node:
##   bsub -q long -J bur -R "select[type=X86_64 && osdistro=rhel && osver=ws8] \
##        rusage[mem=60000]" -o <outdir>/bur.%J.log \
##        ./run_bram_uram_lsf.csh <dcp> <outdir>
###########################################################################
if ( $#argv < 2 ) then
    echo "usage: run_bram_uram_lsf.csh <dcp> <outdir>"
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
$VIVADO -mode batch -notrace -log $OUTDIR/bur_vivado.log \
    -source $HERE/bram_uram_batch_driver.tcl -tclargs $DCP $OUTDIR
