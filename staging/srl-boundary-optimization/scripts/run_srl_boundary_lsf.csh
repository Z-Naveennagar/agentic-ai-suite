#!/bin/csh -f
###########################################################################
## run_srl_boundary_lsf.csh <dcp> <outdir>
## LSF wrapper: open a POST-OPT / PRE-PLACE DCP on a RHEL8 compute node and run the
## SRL Boundary Optimization Advisor in batch.
##
## Submit from the login node:
##   bsub -q long -J srlbound -n 2 \
##        -R "select[ostype==rhelws810 || ostype==rhelws86 || ostype==rhelws89 || ostype==rhelws87] rusage[mem=65536]" \
##        -o <outdir>/srlbound.%J.log \
##        ./run_srl_boundary_lsf.csh <dcp> <outdir>
## Env tunables (LSF forwards them): SRLB_SLACK_MAX SRLB_HB_MAX_LEVELS SRLB_MAX_PATHS
##   SRLB_HIGH_FANOUT SRLB_MED_FANOUT SRLB_SCOPE SRLB_DO_PARTITION SRLB_WARMUP
##   (see detect_srl_boundary.tcl).
###########################################################################
if ( $#argv < 2 ) then
    echo "usage: run_srl_boundary_lsf.csh <dcp> <outdir>"
    exit 1
endif
set DCP    = $argv[1]
set OUTDIR = $argv[2]
# resolve DCP + OUTDIR to absolute paths BEFORE changing directory
if ( "$DCP" !~ /* ) set DCP = $cwd/$DCP
mkdir -p $OUTDIR
if ( "$OUTDIR" !~ /* ) set OUTDIR = $cwd/$OUTDIR
set HERE = `dirname $0`
cd $HERE
set HERE = $cwd
set VIVADO = /proj/primebuilds/2026.1_PRIME_daily_latest/installs/lin64/2026.1/Vivado/bin/vivado
$VIVADO -mode batch -notrace -log $OUTDIR/srl_boundary_vivado.log \
    -source $HERE/srl_boundary_batch_driver.tcl -tclargs $DCP $OUTDIR
