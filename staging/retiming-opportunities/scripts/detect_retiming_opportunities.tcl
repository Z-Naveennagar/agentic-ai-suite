###########################################################################
## detect_retiming_opportunities.tcl
##
## Retiming-opportunity detector for the `retiming-opportunities` skill.
## READ-ONLY by default (no design mutation). Set env SAVE_TAG=1 to also emit a
## sourceable set_retiming_tags.tcl with PSIP_RETIMING_FORWARD/BACKWARD tags.
##
## Usage (batch):
##   vivado -mode batch -source detect_retiming_opportunities.tcl -tclargs <dcp> <outdir>
## Env/arg tunables:
##   LL_MIN  (deep-logic level threshold, default 8)
##   CLOCK   (restrict deep-path analysis to one clock; default all)
##   SAVE_TAG(1 => emit set_retiming_tags.tcl; default 0 = report only)
##   SLACK_MAX      (logic-path sample window; default 0.2 = failing + near-passing)
##   BRAM_SLACK_MAX (WIDER window for paths touching a BRAM/URAM; default 0.5 -
##                   passing-but-tight block-RAM paths are added so retiming can build
##                   extra slack around block RAM, which eases the P&R tool chain)
##
## Passes:
##   A. FORWARD register-merge  -> ff_merge_retiming.{rpt,sum}   (tag = FORWARD)
##   B. Deep FF->FF cones       -> deep_paths.{rpt,csv} + report_timing_<clk>.rpt
##      classified pure-LUT (BACKWARD-retime) vs carry (PIPELINE, not retiming),
##      with _bret/_fret headroom. Delay-dominance 60% gate applied downstream
##      from the report_timing files (see classify note in SKILL.md).
###########################################################################

if {[llength $argv] < 2} { error "usage: -tclargs <dcp> <outdir>" }
set DCP    [lindex $argv 0]
set OUTDIR [lindex $argv 1]
file mkdir $OUTDIR

proc envd {name def} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $def
}
set LL_MIN   [envd LL_MIN 8]
set CLOCKARG [envd CLOCK ""]
set SAVE_TAG [envd SAVE_TAG 0]
set DEEPMAX  [envd DEEP_MAXPATHS 5000]
set SLACKMAX [envd SLACK_MAX 0.2]
set BRAMSLACKMAX [envd BRAM_SLACK_MAX 0.5]
set t0 [clock seconds]

open_checkpoint $DCP

# ---- tag list (register name -> FORWARD|BACKWARD) ----------------------
array set TAG {}

# ---- safety: is a register legal to retime/tag? -----------------------
# Excludes DONT_TOUCH / MARK_DEBUG / ASYNC_REG and already-retimed/replicated names.
proc retime_safe {cellName} {
    set c [get_cells -quiet $cellName]
    if {$c eq ""} { return 0 }
    if {[string tolower [get_property -quiet DONT_TOUCH $c]] eq "true"} { return 0 }
    if {[string tolower [get_property -quiet MARK_DEBUG $c]] eq "true"} { return 0 }
    if {[string tolower [get_property -quiet ASYNC_REG  $c]] eq "true"} { return 0 }
    return 1
}
# already-retimed / replicated by synthesis (timing-driven naming). EXCLUDED from the
# area MERGE pass (merging would undo timing retiming); INCLUDED in the timing pass
# (a _bret/_fret reg that still shows imbalance is a valid further-retiming target).
proc is_retimed {cellName} { return [regexp {_bret|_fret|_replica} $cellName] }

########################################################################
## PASS A — FORWARD register-merge (N registered LUT inputs -> 1 output FF)
########################################################################
puts "PASS_A forward-merge: collecting FF Q pins ..."
set qpins [get_pins -hierarchical -quiet -filter {REF_PIN_NAME == Q}]
set qnets1 [get_nets -quiet -of_objects $qpins -filter {FLAT_PIN_COUNT == 2}]
puts "PASS_A fanout-1 FF-Q nets = [llength $qnets1]"

array set LUTCNT {}
foreach net $qnets1 {
    set lp [get_pins -quiet -leaf -filter {DIRECTION == IN} -of_objects $net]
    if {[llength $lp] != 1} { continue }
    set lcell [get_property -quiet PARENT_CELL $lp]
    if {$lcell eq ""} { continue }
    if {[info exists LUTCNT($lcell)]} {
        incr LUTCNT($lcell)
    } else {
        set lref [get_property -quiet REF_NAME [get_cells -quiet $lcell]]
        if {![regexp {^LUT[1-6]$} $lref]} { continue }
        set LUTCNT($lcell) 1
    }
}
set candLuts {}
foreach {l c} [array get LUTCNT] { if {$c >= 2} { lappend candLuts $l } }
puts "PASS_A candidate LUTs (>=2 fanout-1 FF inputs) = [llength $candLuts]"

# control-set signature (cached)
array set CS {}
proc netname {cell pin} {
    set p [get_pins -quiet $cell/$pin]
    if {$p eq ""} { return "NOPIN" }
    set n [get_nets -quiet -of_objects $p]
    if {$n eq ""} { return "UNCONN" }
    return [get_property -quiet NAME $n]
}
proc ctrlset {cell} {
    global CS
    if {[info exists CS($cell)]} { return $CS($cell) }
    set ref [get_property -quiet REF_NAME [get_cells -quiet $cell]]
    switch -exact -- $ref {
        FDRE { set srpin R } FDSE { set srpin S } FDCE { set srpin CLR } FDPE { set srpin PRE }
        default { set CS($cell) ""; return "" }
    }
    set sig "$ref|C=[netname $cell C]|CE=[netname $cell CE]|SR=[netname $cell $srpin]"
    set CS($cell) $sig
    return $sig
}
# verify: all used LUT inputs are fanout-1 FDxE (or const); return FF list or ""
proc verify_lut {lcell} {
    set lc [get_cells -quiet $lcell]
    if {$lc eq ""} { return "" }
    set ffs {}
    foreach ip [get_pins -quiet -of_objects $lc -filter {DIRECTION == IN}] {
        set net [get_nets -quiet -of_objects $ip]
        if {$net eq ""} { continue }
        set dpin [get_pins -quiet -leaf -filter {DIRECTION == OUT} -of_objects $net]
        if {[llength $dpin] != 1} { return "" }
        set dcell [get_property -quiet PARENT_CELL $dpin]
        set dref  [get_property -quiet REF_NAME [get_cells -quiet $dcell]]
        if {$dref eq "VCC" || $dref eq "GND"} { continue }
        if {![string match FD* $dref]} { return "" }
        set fpc [get_property -quiet FLAT_PIN_COUNT $net]
        if {$fpc ne "" && $fpc != 2} { return "" }
        lappend ffs $dcell
    }
    if {[llength $ffs] < 2} { return "" }
    return $ffs
}

set Rm [open $OUTDIR/ff_merge_retiming.rpt w]
puts $Rm [format "%-7s %-6s %-6s %-8s  %s" "REF" "#FFin" "save" "safe" "LUT  ctrlset | FFs"]
set nQual 0; set nSave 0; set nQualSafe 0; set nSaveSafe 0
foreach L $candLuts {
    set ffs [verify_lut $L]
    if {$ffs eq ""} { continue }
    set sig0 ""; set ok 1
    foreach f $ffs {
        set s [ctrlset $f]
        if {$s eq ""} { set ok 0; break }
        if {$sig0 eq ""} { set sig0 $s } elseif {$s ne $sig0} { set ok 0; break }
    }
    if {!$ok} { continue }
    # safety: every input FF must be retime-safe (not _bret/_fret/dont_touch/async)
    set safe 1
    foreach f $ffs { if {![retime_safe $f] || [is_retimed $f]} { set safe 0; break } }
    set nff [llength $ffs]; set save [expr {$nff - 1}]
    incr nQual; incr nSave $save
    if {$safe} {
        incr nQualSafe; incr nSaveSafe $save
        foreach f $ffs { set TAG($f) FORWARD }
    }
    set lref [get_property -quiet REF_NAME [get_cells -quiet $L]]
    puts $Rm [format "%-7s %-6d %-6d %-8s  %s  {%s} | %s" $lref $nff $save [expr {$safe?"SAFE":"skip"}] $L $sig0 $ffs]
}
close $Rm

set Sm [open $OUTDIR/ff_merge_retiming.sum w]
foreach ln [list \
    "================ FORWARD FF-MERGE (retime N inputs -> 1 output) ================" \
    [format "design                         : %s" [get_property NAME [current_design]]] \
    [format "candidate LUTs (>=2 reg inputs) : %d" [llength $candLuts]] \
    [format "QUALIFYING LUTs (all)           : %d  (FFs saved %d)" $nQual $nSave] \
    [format "SAFE (taggable FORWARD)         : %d  (FFs saved %d)" $nQualSafe $nSaveSafe] \
    "  (SAFE excludes _bret/_fret/_replica, DONT_TOUCH, MARK_DEBUG, ASYNC_REG inputs)"] {
    puts $Sm $ln; puts $ln
}
close $Sm

########################################################################
## PASS B — deep FF->FF cones (backward-retiming vs pipeline)
########################################################################
puts "PASS_B deep paths (LL_MIN=$LL_MIN) ..."
set clocks [get_clocks -quiet]
if {$CLOCKARG ne ""} { set clocks [get_clocks -quiet $CLOCKARG] }

# human-readable report_timing per clock (has logic/route % for the 60% gate)
foreach clk $clocks {
    catch {
        report_timing -to $clk -setup -max_paths 40 -nworst 40 -unique_pins -input_pins \
            -file $OUTDIR/report_timing_[get_property NAME $clk].rpt
    }
}

# structural dump of worst setup paths. For each deep cone we evaluate the
# ADJACENT-STAGE IMBALANCE (this is the real retimeability test - NOT "path is
# critical"). depth_in = levels of the deep cone; depth_out(E) = worst outgoing
# depth from the capture reg; depth_in(S) = worst incoming depth to the launch reg.
#   BACKWARD-tag capture reg E if depth_in - depth_out(E) >= IMBAL_MIN
#   FORWARD-tag  launch reg  S if depth_in - depth_in(S) >= IMBAL_MIN
# (i.e. move the register toward the SHALLOW neighbor that can absorb the levels).
# A move of imbal/2 levels reduces the max stage depth; if imbal < IMBAL_MIN the
# stages are within a small window -> already balanced -> NOT retimeable.
set IMBAL_MIN [envd IMBAL_MIN 3]

proc lut_levels {p} {
    if {$p eq ""} { return 0 }
    set n 0
    foreach c [get_cells -quiet -of_objects $p] {
        if {[string match LUT* [get_property -quiet REF_NAME $c]]} { incr n }
    }
    return $n
}
proc has_carry {p} {
    foreach c [get_cells -quiet -of_objects $p] {
        if {[regexp {LOOKAHEAD8|LUTCY|CARRY} [get_property -quiet REF_NAME $c]]} { return 1 }
    }
    return 0
}
proc depth_from {reg} { return [lut_levels [get_timing_paths -quiet -setup -from [get_cells -quiet $reg] -max_paths 1 -nworst 1]] }
proc depth_to   {reg} { return [lut_levels [get_timing_paths -quiet -setup -to   [get_cells -quiet $reg] -max_paths 1 -nworst 1]] }
# only a real D-FF register can be MOVED by retiming (BRAM/DSP/LUTRAM cannot).
proc is_ff {cell} { return [string match FD* [get_property -quiet REF_NAME [get_cells -quiet $cell]]] }
# a PURE LUT (LUT1-6 / LUT6_2) - NOT a carry variant (LUT6CY / LUTCY1/2 / LOOKAHEAD8 / CARRY*).
proc is_pure_lut {ref} {
    if {[regexp {CY|LOOKAHEAD|CARRY} $ref]} { return 0 }
    return [string match LUT* $ref]
}
# a BLOCK-RAM / UltraRAM endpoint (RAMB18/36, URAM288, block-RAM FIFO18/36). These
# cannot themselves be moved, but a FF on the LUT cone next to them can be retimed to
# build extra setup slack AROUND the block RAM (helps placement/routing of hard blocks).
proc is_bram_uram {cell} {
    return [regexp {^(RAMB|URAM|FIFO18|FIFO36)} [get_property -quiet REF_NAME [get_cells -quiet $cell]]]
}
# BACKWARD ok: the LAST primitive driving the endpoint FF's D pin is a PURE LUT
# (arithmetic/carry EARLIER in the cone is fine - the FF moves back across the pure LUT).
proc backward_ok {ff} {
    set d [get_pins -quiet $ff/D]
    if {$d eq ""} { return 0 }
    set drv [get_pins -quiet -leaf -filter {DIRECTION == OUT} -of_objects [get_nets -quiet -of_objects $d]]
    if {[llength $drv] != 1} { return 0 }
    return [is_pure_lut [get_property -quiet REF_NAME [get_cells -quiet [get_property -quiet PARENT_CELL $drv]]]]
}
# FORWARD ok: the launch FF's Q drives at least one PURE LUT (first primitive on the cone).
proc forward_ok {ff} {
    set q [get_pins -quiet $ff/Q]
    if {$q eq ""} { return 0 }
    foreach ld [get_pins -quiet -leaf -filter {DIRECTION == IN} -of_objects [get_nets -quiet -of_objects $q]] {
        if {[is_pure_lut [get_property -quiet REF_NAME [get_cells -quiet [get_property -quiet PARENT_CELL $ld]]]]} { return 1 }
    }
    return 0
}

set Bc [open $OUTDIR/deep_paths.csv w]
puts $Bc "idx,slack,src_clk,dst_clk,depth_in,depth_out_E,depth_in_S,carry,samedomain,end_ff,start_ff,launch_reg,capture_reg,cap_retimed,imbalance,tag_reg,tag_dir,bram"
# Primary sample: FAILING + NEAR-PASSING logic paths (setup slack < SLACK_MAX).
set paths [get_timing_paths -setup -max_paths $DEEPMAX -nworst 1 -unique_pins -slack_lesser_than $SLACKMAX]
# Dedicated BRAM/URAM sample: block-RAM paths that already MEET timing but only with a
# tight positive margin (slack < BRAM_SLACK_MAX). Failing block-RAM paths are already
# covered by the primary sample; here we ADD the passing-but-tight ones so retiming can
# build extra slack around the hard block (BRAM/URAM), which helps the P&R tool chain.
set bramcells [get_cells -hier -quiet -filter {REF_NAME =~ RAMB* || REF_NAME =~ URAM* || REF_NAME =~ FIFO18* || REF_NAME =~ FIFO36*}]
set brampaths {}
if {[llength $bramcells]} {
    catch { lappend brampaths {*}[get_timing_paths -quiet -setup -to   $bramcells -max_paths $DEEPMAX -nworst 1 -unique_pins -slack_lesser_than $BRAMSLACKMAX] }
    catch { lappend brampaths {*}[get_timing_paths -quiet -setup -from $bramcells -max_paths $DEEPMAX -nworst 1 -unique_pins -slack_lesser_than $BRAMSLACKMAX] }
}
puts "PASS_B primary paths = [llength $paths] ; BRAM/URAM paths (slack < $BRAMSLACKMAX) = [llength $brampaths]"
set allpaths [concat $paths $brampaths]
set idx 0; set nBack 0; set nFwd 0; set nCarryPath 0; set nCarryBoundary 0; set nDeep 0; set nBalanced 0; set nXdom 0; set nNoFF 0; set nBramPath 0; set nBramCand 0; set CAND {}
array set SEEN {}
foreach p $allpaths {
    set spin [get_property -quiet STARTPOINT_PIN $p]
    set epin [get_property -quiet ENDPOINT_PIN $p]
    set pkey "$spin|$epin"
    if {[info exists SEEN($pkey)]} { continue } ;# a path can appear in both samples
    set SEEN($pkey) 1
    incr idx
    set slack [get_property -quiet SLACK $p]
    set sclk  [get_property -quiet STARTPOINT_CLOCK $p]
    set dclk  [get_property -quiet ENDPOINT_CLOCK $p]
    set sreg [get_property -quiet PARENT_CELL [get_pins -quiet $spin]]
    set ereg [get_property -quiet PARENT_CELL [get_pins -quiet $epin]]
    set bram [expr {[is_bram_uram $sreg] || [is_bram_uram $ereg]}]
    set depth_in [lut_levels $p]
    if {$depth_in < $LL_MIN} { continue }
    incr nDeep
    if {$bram} { incr nBramPath }
    set carry [has_carry $p] ;# informational: does the cone contain arithmetic/carry cells
    if {$carry} { incr nCarryPath }
    set eret [expr {[regexp {_bret|_fret} $ereg] ? 1 : 0}]
    set samedom [expr {$sclk eq $dclk && $sclk ne ""}]
    set tagreg ""; set tagdir ""; set out_E ""; set in_S ""; set imbal ""
    set effF [is_ff $ereg]   ;# capture is a FF  -> eligible for BACKWARD (start may be BRAM/DSP)
    set sisF [is_ff $sreg]   ;# launch  is a FF  -> eligible for FORWARD  (end   may be BRAM/DSP)
    if {!$samedom} {
        incr nXdom
    } elseif {!$effF && !$sisF} {
        incr nNoFF ;# neither end is a movable FF (e.g. BRAM->..->BRAM) -> nothing to retime
    } else {
        # Retimeable across the register boundary iff the primitive AT that boundary is a
        # PURE LUT (LUT1-6). Carry/arith structures EARLIER in the cone are fine.
        set imbal_back -9999; set imbal_fwd -9999
        if {$effF && [retime_safe $ereg] && [backward_ok $ereg]} { set out_E [depth_from $ereg]; set imbal_back [expr {$depth_in - $out_E}] }
        if {$sisF && [retime_safe $sreg] && [forward_ok $sreg]}            { set in_S  [depth_to  $sreg]; set imbal_fwd  [expr {$depth_in - $in_S}] }
        if {$imbal_back == -9999 && $imbal_fwd == -9999} {
            incr nCarryBoundary ;# the FF's boundary primitive is a carry element -> can't retime here
        } elseif {$imbal_back >= $imbal_fwd && $imbal_back >= $IMBAL_MIN && ![info exists TAG($ereg)]} {
            set tagreg $ereg; set tagdir BACKWARD; set imbal $imbal_back
            set TAG($ereg) BACKWARD; incr nBack
            if {$bram} { incr nBramCand }
            set moved [expr {$imbal_back/2}]
            set newmax [expr {($depth_in-$moved) > ($out_E+$moved) ? ($depth_in-$moved) : ($out_E+$moved)}]
            lappend CAND [list [expr {$depth_in-$newmax}] $ereg BACKWARD $depth_in $out_E $imbal_back $newmax $slack $sclk $eret $bram]
        } elseif {$imbal_fwd >= $IMBAL_MIN && ![info exists TAG($sreg)]} {
            set tagreg $sreg; set tagdir FORWARD; set imbal $imbal_fwd
            set TAG($sreg) FORWARD; incr nFwd
            if {$bram} { incr nBramCand }
            set moved [expr {$imbal_fwd/2}]
            set newmax [expr {($depth_in-$moved) > ($in_S+$moved) ? ($depth_in-$moved) : ($in_S+$moved)}]
            lappend CAND [list [expr {$depth_in-$newmax}] $sreg FORWARD $depth_in $in_S $imbal_fwd $newmax $slack $sclk [is_retimed $sreg] $bram]
        } else {
            incr nBalanced ;# imbalance < IMBAL_MIN -> not retimeable
        }
    }
    puts $Bc "$idx,$slack,$sclk,$dclk,$depth_in,$out_E,$in_S,$carry,$samedom,$effF,$sisF,$sreg,$ereg,$eret,$imbal,$tagreg,$tagdir,$bram"
}
close $Bc

# ---- ranked, REASONED candidate report (robustness: justify each selection) ----
set Cr [open $OUTDIR/retiming_candidates.rpt w]
puts $Cr "RANKED RETIMING CANDIDATES (by estimated logic-levels saved on the critical stage)"
puts $Cr "Sampled from FAILING + NEAR-PASSING paths (setup slack < SLACK_MAX). Each candidate passes:"
puts $Cr "same clock domain; a PURE LUT at the moved FF's boundary (carry allowed EARLIER in the cone);"
puts $Cr "not DONT_TOUCH/MARK_DEBUG/ASYNC_REG; and adjacent-stage imbalance >= IMBAL_MIN so balancing"
puts $Cr "strictly reduces the MAX stage depth. Already-retimed (_bret/_fret) cells ARE included when"
puts $Cr "they still show imbalance (flagged in the reason line)."
puts $Cr "Paths touching a BRAM/URAM are ALSO sampled up to a wider slack window (BRAM_SLACK_MAX) so"
puts $Cr "retiming can build extra slack around block RAM even when the path already meets timing."
puts $Cr ""
puts $Cr [format "%-4s %-6s %-9s %-6s %-6s %-6s %-7s %-9s  %s" "rank" "saved" "dir" "critD" "donD" "imbal" "newMax" "slack" "register"]
set rank 0
foreach e [lsort -integer -decreasing -index 0 $CAND] {
    incr rank
    lassign $e saved reg dir cd dd imb nm slk clk ret bram
    set rmark [expr {$ret ? " (already-retimed cell)" : ""}]
    set bmark [expr {$bram ? " (BRAM/URAM-adjacent - builds slack around block RAM)" : ""}]
    puts $Cr [format "%-4d %-6d %-9s %-6d %-6d %-6d %-7d %-9s  %s" $rank $saved $dir $cd $dd $imb $nm $slk $reg]
    puts $Cr "     reason: ${dir}-retime moves ~[expr {$imb/2}] level(s) from the depth-$cd critical stage into its depth-$dd neighbor; balanced max depth ~$nm (was $cd) => ~$saved fewer levels. slack=$slk clk=$clk.$rmark$bmark Re-check hold slack on a placed/routed DCP before committing."
}
close $Cr
puts "WROTE $OUTDIR/retiming_candidates.rpt  ([llength $CAND] ranked candidates)"

set Sb [open $OUTDIR/deep_paths.sum w]
foreach ln [list \
    "============ DEEP FF->FF CONES (retimeable only if adjacent-stage imbalance) ============" \
    [format "sampled paths                   : top %d setup paths with slack < %s (failing + near-passing)" $DEEPMAX $SLACKMAX] \
    [format "BRAM/URAM widened window        : slack < %s (adds passing-but-tight block-RAM paths)" $BRAMSLACKMAX] \
    [format "LL_MIN / IMBAL_MIN              : %d / %d" $LL_MIN $IMBAL_MIN] \
    [format "deep cones (>= LL_MIN LUTs)     : %d" $nDeep] \
    [format "  of which touch a BRAM/URAM    : %d" $nBramPath] \
    [format "cones containing carry/arith    : %d  (informational; still retimeable if the FF-boundary primitive is a pure LUT)" $nCarryPath] \
    [format "carry AT the FF boundary (SKIP) : %d  (LUT6CY/LUTCY/LOOKAHEAD drives the FF - cannot retime across it)" $nCarryBoundary] \
    [format "cross-domain (SKIP)             : %d  (launch clk != capture clk)" $nXdom] \
    [format "no movable FF end (SKIP)        : %d  (e.g. BRAM->..->BRAM; nothing to move)" $nNoFF] \
    [format "balanced/small-window (REJECT)  : %d  (imbalance < IMBAL_MIN - nothing to rebalance)" $nBalanced] \
    [format "BACKWARD tag candidates         : %d  (capture FF; deep incoming cone, shallow outgoing; start may be BRAM)" $nBack] \
    [format "FORWARD  tag candidates         : %d  (launch FF;  deep outgoing cone, shallow incoming; end may be BRAM)" $nFwd] \
    [format "  of which are BRAM/URAM-adjacent: %d  (retimed to build extra slack around block RAM for P&R)" $nBramCand] \
    "RULE: a cone is retimeable ONLY when a neighbor stage can ABSORB the moved" \
    "      levels (imbalance >= IMBAL_MIN) so the MAX stage depth strictly drops -" \
    "      not merely because the path is critical. See deep_paths.csv per-path." \
    "NOTE (routed DCP only): additionally apply the >60% logic-delay gate + hold-slack" \
    "      safety from report_timing_<clk>.rpt before final ranking (see SKILL.md)." ] {
    puts $Sb $ln; puts $ln
}
close $Sb

########################################################################
## Optional: emit sourceable tag file
########################################################################
if {$SAVE_TAG == 1} {
    set Tg [open $OUTDIR/set_retiming_tags.tcl w]
    puts $Tg "## set_retiming_tags.tcl  (auto-generated [clock format [clock seconds]])"
    puts $Tg "## Placer retiming tags. Source in the open design. Self-validating."
    set nf 0; set nb 0
    foreach {cell dir} [array get TAG] {
        set prop [expr {$dir eq "FORWARD" ? "PSIP_RETIMING_FORWARD" : "PSIP_RETIMING_BACKWARD"}]
        puts $Tg "set_property $prop TRUE \[get_cells {$cell}\]"
        if {$dir eq "FORWARD"} { incr nf } else { incr nb }
    }
    close $Tg
    puts "WROTE $OUTDIR/set_retiming_tags.tcl  (FORWARD=$nf BACKWARD=$nb)"
}

puts "RETIMING_DONE in [expr {[clock seconds]-$t0}] s  -> outputs in $OUTDIR"
