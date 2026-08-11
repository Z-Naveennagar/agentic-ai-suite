#!/bin/csh -f
###########################################################################
## run_retiming_lsf.csh
## LSF wrapper: open a DCP on the compute node and run the retiming detector.
## Usage (submit from the login node):
##   bsub -q long -J retime -n 2 \
##     -R "select[ostype==rhelws810 || ostype==rhelws86 || ostype==rhelws89 || ostype==rhelws87] rusage[mem=65536]" \
##     -o <outdir>/retime.%J.log \
##     ./run_retiming_lsf.csh <dcp_path> <outdir>
###########################################################################
if ( $#argv < 2 ) then
    echo "usage: run_retiming_lsf.csh <dcp_path> <outdir>"
    exit 1
endif

set DCP = $argv[1]
set OUTDIR = $argv[2]
set SCRIPTDIR = `dirname $0`
# resolve SCRIPTDIR to an ABSOLUTE path (we cd to OUTDIR below, so relative breaks)
cd $SCRIPTDIR
set SCRIPTDIR = `pwd`
set VIVADO = /proj/primebuilds/2026.1_PRIME_daily_latest/installs/lin64/2026.1/Vivado/bin/vivado

mkdir -p $OUTDIR
cd $OUTDIR

$VIVADO -mode batch -nojournal -notrace \
    -log $OUTDIR/retiming_vivado.log \
    -source $SCRIPTDIR/detect_retiming_opportunities.tcl \
    -tclargs $DCP $OUTDIR
