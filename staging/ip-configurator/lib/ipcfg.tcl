# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# ============================================================
# ipcfg.tcl - Generic, IP-agnostic helpers for the ip-configurator skill
#
# Source ONCE per Vivado session, after a block design is open:
#     source <skill_dir>/lib/ipcfg.tcl
#
# Every proc is IP-agnostic: no IP names, VLNVs, or parameter names are
# baked in. All IP-specific values (VLNV, CONFIG dict, automation rule,
# stub pin) are passed in by the caller, who discovers them from
# vivado_doc_search and Vivado's own error/read-back feedback.
#
# Procs return a single structured line the agent parses:
#     SUCCESS:<detail>
#     CONFIGURE_FAIL:<TYPE>:<detail>
# where <TYPE> is one of:
#     CREATE_ERROR PARAM_NOT_FOUND VALUE_OUT_OF_RANGE READ_ONLY
#     NOT_SUPPORTED PARAM_DISABLED AUTOMATION_ERROR STUB_ERROR UNKNOWN
# ============================================================

namespace eval ipcfg {
    variable bd_file ""
    # Operating mode: "benchmark" (default) = one throwaway cell per prompt,
    # ipcfg::cleanup deletes it between prompts. "assemble" = persistent build
    # (the ipi-assembler skill): cells must SURVIVE, so ipcfg::cleanup becomes a
    # no-op guard. Set with ipcfg::set_mode. Everything else (create_cell_cfg,
    # verify_intent, audit_intent, discover_params, the learned cache) is reused
    # unchanged across both modes.
    variable mode "benchmark"
    # lib dir (resolved at source time) -> locate the cache engine + store
    variable dir [file dirname [file normalize [info script]]]
    variable cache_engine [file join $dir ipcfg_cache.py]
    variable cache_file   [file normalize [file join $dir .. cache learned_params.json]]
}

# --- Operating-mode control (benchmark vs assemble) ---
# In "assemble" mode the persistent design is being built, so destructive
# cleanup is refused. Returns the active mode.
proc ipcfg::set_mode {m} {
    variable mode
    if {$m ni {benchmark assemble}} {
        return "ERR:bad mode '$m' (expected benchmark|assemble)"
    }
    set mode $m
    return "SUCCESS:mode=$mode"
}
proc ipcfg::get_mode {} {
    variable mode
    return $mode
}

# --- internal: resolve the .bd file (for close/reopen during a part swap) ---
proc ipcfg::_bd_file {} {
    variable bd_file
    if {$bd_file ne ""} { return $bd_file }
    set bf [get_files -quiet *.bd]
    if {[llength $bf] > 0} { return [lindex $bf 0] }
    return "benchmark_bd.bd"
}

# Optionally pin the bd file name explicitly (else it is auto-detected).
proc ipcfg::set_bd_file {f} {
    variable bd_file
    set bd_file $f
    return "SUCCESS:bd_file=$f"
}

# --- internal: light value normalization for stuck-value comparison ---
proc ipcfg::_norm {v} {
    set v [string trim $v]
    set v [string tolower $v]
    if {$v eq "true"}  {set v 1}
    if {$v eq "false"} {set v 0}
    # collapse trailing zeros on decimals: 100.000 -> 100
    if {[regexp {^-?[0-9]+\.[0-9]+$} $v]} {
        set v [string trimright $v 0]
        set v [string trimright $v .]
    }
    return $v
}

proc ipcfg::_is_num {s} { return [string is double -strict $s] }

# --- internal: is `cur` a legal NEIGHBOR of the requested `want`? ---
# Used to tell "the IP resolved my request to a nearby legal value" (RESOLVED)
# apart from "the request snapped back to default / elsewhere" (REVERTED).
#   - validset given: cur is a member but want is not (IP picked nearest legal)
#   - else both numeric: within 0.5 absolute or 1% relative of want
proc ipcfg::_neighbor {cur want {validset {}}} {
    if {[llength $validset] > 0} {
        set inset 0; set wantinset 0
        foreach m $validset {
            set nm [ipcfg::_norm $m]
            if {$nm eq $cur}  {set inset 1}
            if {$nm eq $want} {set wantinset 1}
        }
        if {$inset && !$wantinset} { return 1 }
    }
    if {[ipcfg::_is_num $cur] && [ipcfg::_is_num $want]} {
        set d [expr {abs(double($cur) - double($want))}]
        set denom [expr {abs($want) > 0 ? abs(double($want)) : 1.0}]
        if {$d <= 0.5 || ($d / $denom) <= 0.01} { return 1 }
    }
    return 0
}

# --- Resolved-vs-reverted classification (idea #2) ---
# Classify what happened to ONE key after an apply, using its pre-apply default.
#   want: requested value ("" => the key was NOT requested - a sibling scan)
#   base: pre-apply (default) value     cur: post-apply value
# Returns for requested keys:
#   EXACT    - cur == want
#   RESOLVED - cur is the IP's nearest-legal neighbor of want (NOT a miss)
#   REVERTED - cur snapped back to default, or landed somewhere unrelated
# and for unrequested keys (want==""):  UNCHANGED | CHANGED (side effect).
proc ipcfg::classify_change {want base cur {validset {}}} {
    set nb [ipcfg::_norm $base]
    set nc [ipcfg::_norm $cur]
    if {$want eq ""} { return [expr {$nc eq $nb ? "UNCHANGED" : "CHANGED"}] }
    set nw [ipcfg::_norm $want]
    if {$nc eq $nw}                            { return "EXACT" }
    if {[ipcfg::_neighbor $nc $nw $validset]}  { return "RESOLVED" }
    return "REVERTED"
}

# --- Phase 0: part swap / restore (close + reopen the bd around the change) ---
# Guarded: a part swap is destructive to a design-in-progress (existing IP may be
# incompatible with / need upgrading for the new part). If other bd_cells already
# exist and force==0, this REFUSES to swap and returns a WARN so the caller can
# confirm with the user (design mode) before forcing. On an empty/isolated BD it
# swaps freely (benchmark mode uses throwaway cells).
proc ipcfg::ensure_part {target {force 0}} {
    set orig [get_property PART [current_project]]
    if {$orig eq $target} { return "NOSWAP:$orig" }
    set others [llength [get_bd_cells -quiet]]
    if {$others > 0 && !$force} {
        return "WARN:SWAP_BLOCKED:$others existing cell(s) may be part-incompatible; confirm before swapping $orig->$target (call with force=1 to override)"
    }
    set bd [ipcfg::_bd_file]
    close_bd_design [current_bd_design]
    set_property PART $target [current_project]
    open_bd_design $bd
    return "SWAP:$orig->$target"
}

# Guarded in the mirror image of ensure_part: restoring a part that cannot
# support a cell built on the swapped part silently DROPS that cell. The IP you
# were asked to build is then simply gone -- and since the design is graded from
# a read-back taken AFTER you finish, a run that swapped, built and configured
# correctly scores zero with nothing in any error message to explain it. So
# refuse, and say which cells would be lost.
proc ipcfg::restore_part {orig {force 0}} {
    if {[get_property PART [current_project]] eq $orig} { return "NOSWAP:$orig" }
    if {!$force} {
        set doomed {}
        foreach c [get_bd_cells -quiet] {
            set v [get_property -quiet VLNV $c]
            if {$v eq ""} { continue }
            set sp [get_property -quiet SUPPORTED_PARTS [get_ipdefs -quiet $v]]
            if {[llength $sp] && [lsearch -exact $sp $orig] < 0} {
                lappend doomed [get_property NAME $c]
            }
        }
        if {[llength $doomed]} {
            return "WARN:RESTORE_BLOCKED:restoring $orig would DROP $doomed\
(unsupported on that part). Delete them first (ipcfg::cleanup <cell> $orig, which\
orders it correctly) or leave the part swapped -- the design is read back after\
you finish, so a cell dropped here is a cell you never built. force=1 to override"
        }
    }
    set bd [ipcfg::_bd_file]
    close_bd_design [current_bd_design]
    set_property PART $orig [current_project]
    open_bd_design $bd
    return "RESTORED:$orig"
}

# --- Phase 1: VLNV pre-validation (version-free prefix, e.g. xilinx.com:ip:axi_gpio) ---
# CATALOG MEMBERSHIP ONLY -- this is NOT a part-availability test. `get_ipdefs`
# lists IPs the current part cannot instantiate: on 2026.1/xc2ve3558 this returns
# 1 for clk_wizard, which then fails create_bd_cell with [BD 5-683]. Use
# ipcfg::ip_availability for the part question.
proc ipcfg::vlnv_ok {vlnv} {
    return [expr {[llength [get_ipdefs -quiet -filter "VLNV =~ \"$vlnv:*\""]] > 0}]
}

# --- Phase 1 (gate): part-aware availability over a CANDIDATE SHORTLIST ---
# vlnv_ok is a validator (is the name I already picked present?); this is a
# SELECTOR aid, and it separates two failures a single boolean conflates:
#
#   ABSENT     -- not in this release's catalog at all: renamed or dropped
#                 (2026.1 ps11 -> ps_wizard). Reports catalog neighbours.
#   WRONG_PART -- in the catalog, but the part cannot instantiate it. This is
#                 the create-time [BD 5-683], predicted BEFORE the wasted create.
#                 Reports concrete parts that DO support it.
#   AVAILABLE  -- instantiable here and now.
#   UNKNOWN    -- the ipdef publishes no SUPPORTED_PARTS. Deliberately NOT
#                 reported as WRONG_PART: a false WRONG_PART would trigger a
#                 destructive part swap that was never needed.
#
# The verdict is the ipdef's own SUPPORTED_PARTS list, which on 2026.1 predicts
# [BD 5-683] exactly (verified: clk_wizard excludes xc2ve3558 and fails to
# create; clkx5_wiz includes it and creates). No family-regex parsing, no
# component.xml scraping, no static part map.
#
# `candidates` is the shortlist you are choosing BETWEEN -- pass all of it. A
# single pre-chosen name reduces this to a validator and defeats the point, so
# entries may instead be catalog GLOBS (`*clk*wiz*`), which are expanded against
# the release's catalog: that way the shortlist is DISCOVERED from the prompt's
# function words rather than pre-committed to the first name that came to mind.
# A one-name shortlist is reported as such (`SHORTLIST_OF_1`) unless an explicit
# `part` was passed, which marks the call as a swap-target confirmation.
#
# `part` defaults to the project's, and can be set to a prospective swap target
# to confirm it BEFORE the destructive swap.
#
# Returns ONE line (a Tcl dict after the "IPAVAIL:" tag):
#   IPAVAIL: part=<p> clk_wizard=WRONG_PART:xilinx.com:ip:clk_wizard:1.0:parts={xcvc1902-... ...}:devices=63 \
#            clkx5_wiz=AVAILABLE:xilinx.com:ip:clkx5_wiz:1.0 ps11=ABSENT:near={xilinx.com:ip:ps_wizard:1.0 ...}
proc ipcfg::ip_availability {candidates {part ""} {maxparts 8}} {
    set confirming [expr {$part ne ""}]
    if {$part eq ""} {
        if {[catch {set part [get_property PART [current_project]]}]} {
            return "IPAVAIL_ERR:no current project and no part given"
        }
    }
    # Trailing grade/speed tokens of the current part (e.g. 2MP-e-S). A swap
    # target that keeps them changes only the device, which is the smallest
    # move that can make the IP instantiable.
    set grade [join [lrange [split $part -] 2 end] -]
    set maxcand 16
    set names {}
    set nomatch {}
    foreach cand $candidates {
        set n [ipcfg::_ip_name $cand]
        if {![string match {*[*?]*} $n]} {
            if {$n ni $names} { lappend names $n }
            continue
        }
        set hits {}
        foreach d [lsort [get_ipdefs -quiet *:${n}:*]] {
            set nm [lindex [split $d :] 2]
            if {$nm ni $hits} { lappend hits $nm }
        }
        if {![llength $hits]} { lappend nomatch $n; continue }
        foreach nm $hits { if {$nm ni $names} { lappend names $nm } }
    }
    set extra 0
    if {[llength $names] > $maxcand} {
        set extra [expr {[llength $names] - $maxcand}]
        set names [lrange $names 0 [expr {$maxcand - 1}]]
    }
    set out {}
    set wrongpart {}
    set available {}
    foreach name $names {
        set r [ipcfg::resolve_vlnv $name]
        if {[string match "VLNV_CANDIDATES:*" $r]} {
            lappend out "$name=ABSENT:near=[string range $r 16 end]"
            continue
        }
        if {[string match "VLNV_NONE:*" $r]} {
            lappend out "$name=ABSENT:near={}"
            continue
        }
        set vlnv [string range $r 5 end]
        set sp [get_property -quiet SUPPORTED_PARTS [get_ipdefs -quiet $vlnv]]
        if {[llength $sp] == 0} {
            lappend out "$name=UNKNOWN:$vlnv"
        } elseif {[lsearch -exact $sp $part] >= 0} {
            lappend out "$name=AVAILABLE:$vlnv"
            lappend available $name
            set disp($name) [get_property -quiet DISPLAY_NAME [get_ipdefs -quiet $vlnv]]
        } else {
            lappend out "$name=WRONG_PART:$vlnv:parts={[ipcfg::_suggest_parts $sp $grade $maxparts]}:devices=[llength [ipcfg::_devices $sp]]"
            lappend wrongpart $name
            set disp($name) [get_property -quiet DISPLAY_NAME [get_ipdefs -quiet $vlnv]]
        }
    }
    foreach n $nomatch { lappend out "$n=NO_CATALOG_MATCH" }
    # Same DISPLAY_NAME + disjoint part support = ONE IP split across device
    # generations, not two competing IPs. 2026.1 ships "Clocking Wizard" twice:
    # clk_wizard covers Versal Gen1 (0 xc2ve parts) and clkx5_wiz covers Gen2
    # (375 xc2ve parts, none of Gen1's). On a Gen2 part the AVAILABLE one IS the
    # documented IP for that device, so swapping away to reach the other name
    # would be downgrading the device to use an older edition of the same core.
    # This must be settled here, because from the outside the pair looks exactly
    # like the wrong-IP substitution the next clause exists to prevent.
    set variants {}
    set genuine {}
    foreach w $wrongpart {
        set dw [string trim [expr {[info exists disp($w)] ? $disp($w) : ""}]]
        set matched ""
        foreach a $available {
            set da [string trim [expr {[info exists disp($a)] ? $disp($a) : ""}]]
            if {$dw ne "" && [string equal -nocase $dw $da]} { set matched $a; break }
        }
        if {$matched ne ""} { lappend variants "$w~$matched" } else { lappend genuine $w }
    }
    if {[llength $variants]} {
        lappend out "VARIANT_OF:{$variants}:same DISPLAY_NAME -- these are the SAME\
IP partitioned by device generation, so the AVAILABLE one is the correct IP for\
this part: USE IT and do NOT swap. (Swapping would move to an older device\
generation to reach an older edition of the same core.)"
    }
    # Whatever is left is the real hazard: a candidate that needs a part swap
    # sitting next to a DIFFERENT IP that happens to work here. A bare verdict
    # table reads as an invitation to take the one that works, so the rule has to
    # travel WITH the facts rather than live only in the skill prose.
    if {[llength $genuine] && [llength $available]} {
        lappend out "SELECT_RULE:{$genuine} need a part swap while {$available}\
work here, and they are DIFFERENT IPs (different DISPLAY_NAME) -- NOT\
interchangeable. Decide from DOCUMENTATION which one implements the requested\
function; if that one is WRONG_PART, SWAP THE PART (ipcfg::ensure_part -- it\
proceeds on its own when the BD holds no other cells). WRONG_PART is a DEVICE\
mismatch, not a capability limit: it is NOT grounds for a negative result and the\
WRONG_PART IP is NOT 'unavailable to you'. Taking the AVAILABLE one instead is a\
wrong-IP bug that NEVER errors -- it builds, configures and verifies clean"
    }
    if {$extra > 0} { lappend out "TRUNCATED=$extra" }
    # A one-name shortlist is the misuse this proc exists to prevent: it can only
    # confirm a name already chosen, so an IP that is WRONG_PART here is never
    # even compared against. Say so, and name the cheap correct call. Suppressed
    # when a part was passed, since that call IS a single-name confirmation.
    if {!$confirming && [llength $names] < 2} {
        lappend out "SHORTLIST_OF_1:validator-only-call:re-run with every\
candidate you are choosing between, or a catalog glob (e.g. {*clk*wiz*}), so the\
IP is chosen by documented function against what this release ships"
    }
    return "IPAVAIL: part=$part [join $out " "]"
}

# --- internal: bare IP name from a name or a (possibly partial) VLNV ---
proc ipcfg::_ip_name {hint} {
    set h [string trim $hint]
    if {[string first : $h] >= 0} {
        set p [split $h :]
        if {[llength $p] >= 3} { return [lindex $p 2] }
    }
    return $h
}

# --- internal: distinct device stems in a parts list (xcvc1902-vsva2197-... -> xcvc1902) ---
proc ipcfg::_devices {parts} {
    set d {}
    foreach p $parts {
        set s [lindex [split $p -] 0]
        if {$s ni $d} { lappend d $s }
    }
    return $d
}

# --- internal: compact swap-target suggestions from a SUPPORTED_PARTS list ---
# A supported list runs to ~1600 entries across ~60 devices, which is useless as
# a report. Narrow to parts carrying the current part's grade (so only the device
# changes), then one per device so the caller sees real alternatives rather than
# ten packages of the same chip. Falls back to the raw head when no grade matches.
proc ipcfg::_suggest_parts {parts grade max} {
    set pool $parts
    if {$grade ne ""} {
        set matched [lsearch -all -inline $parts *-$grade]
        if {[llength $matched]} { set pool $matched }
    }
    set seen {}
    set out {}
    foreach p [lsort $pool] {
        set s [lindex [split $p -] 0]
        if {$s in $seen} { continue }
        lappend seen $s
        lappend out $p
        if {[llength $out] >= $max} { break }
    }
    return $out
}

# --- Phase 2: create the cell (idempotent) ---
proc ipcfg::create_cell {vlnv cell} {
    if {[llength [get_bd_cells -quiet $cell]] == 0} {
        if {[catch {create_bd_cell -type ip -vlnv $vlnv $cell} e]} {
            return "CONFIGURE_FAIL:CREATE_ERROR:$e"
        }
    }
    return "SUCCESS:created $cell"
}

# --- Phase 3: apply a -dict with structured error classification ---
proc ipcfg::apply_dict {cell d} {
    if {[llength $d] == 0} { return "SUCCESS:no-params" }
    if {[catch {set_property -dict $d [get_bd_cells $cell]} e]} {
        set t "UNKNOWN"
        if {[string match {*does not exist*} $e]}      {set t "PARAM_NOT_FOUND"}
        if {[string match {*is out of the range*} $e]} {set t "VALUE_OUT_OF_RANGE"}
        if {[string match {*read-only*} $e]}           {set t "READ_ONLY"}
        if {[string match {*It is read-only*} $e]}     {set t "READ_ONLY"}
        if {[string match {*not supported*} $e]}       {set t "NOT_SUPPORTED"}
        if {[string match {*disabled*} $e]}            {set t "PARAM_DISABLED"}
        return "CONFIGURE_FAIL:$t:$e"
    }
    return "SUCCESS:applied"
}

# --- Phase 3 verification: detect keys that did NOT stick (silent revert) ---
# Returns "" if all stuck, else a list of offending keys with detail.
# Handles scalar values (normalized compare) and nested *_CONFIG dicts
# (checks each requested sub-key appears in the read-back string).
proc ipcfg::verify_stuck {cell d} {
    set bad {}
    foreach {k v} $d {
        if {[catch {set cur [get_property $k [get_bd_cells $cell]]}]} {
            lappend bad "${k}(missing)"
            continue
        }
        if {[string match {*_CONFIG} $k]} {
            # nested dict: confirm each requested sub-key/value is present
            foreach {sk sv} $v {
                if {[string first $sk $cur] < 0} {
                    lappend bad "${k}/${sk}(missing)"
                } elseif {[string first $sv $cur] < 0} {
                    lappend bad "${k}/${sk}(reverted)"
                }
            }
        } else {
            if {[ipcfg::_norm $cur] ne [ipcfg::_norm $v]} {
                lappend bad "${k}(=$cur,want=$v)"
            }
        }
    }
    return $bad
}

# --- internal: does a value read as a boolean, and which way? ---
# Returns 1 (true), 0 (false), or "" when the value is not boolean-shaped, so a
# comma-list (true,true,false) or an enum can never be mistaken for a flag.
proc ipcfg::_bool {v} {
    switch -- [string tolower [string trim $v]] {
        true  - 1 - yes - on  { return 1 }
        false - 0 - no  - off { return 0 }
    }
    return ""
}

# --- Phase 3 verification: detect INERT writes (gated attribute, flag still off) ---
# The failure verify_stuck cannot see. An attribute parameter whose feature is
# switched off elsewhere is NOT rejected: the write succeeds, reads back exactly,
# and every existing check is clean -- but the IP never grows the port, so the
# requested behaviour is silently absent. Measured on clkx5_wiz:
#   set CONFIG.RESET_TYPE ACTIVE_LOW, USE_RESET left false
#     -> RESET_TYPE reads ACTIVE_LOW, pins are {clk_in1 clk_out1}: no reset at all
#   then set USE_RESET true -> pins gain {resetn}
# Detection is mechanical and per-cell: for each REQUESTED key, look for a
# sibling parameter on the SAME cell whose name is a known enabler form of the
# key's feature token, and whose current value reads false. Nothing about any
# specific IP is assumed -- an IP without such a sibling reports nothing.
# Returns "" when clean, else "INERT:<key>:enabler=<CONFIG.flag>=<value> ...".
# An enabler already requested truthily in the same dict is not reported.
proc ipcfg::check_enablers {cell d} {
    if {[catch {set obj [get_bd_cells $cell]}]} { return "" }
    # Case-insensitive index of the cell's own parameter names: IPs are not
    # consistent about case (axi_gpio has C_IS_DUAL, axi_dma has c_include_sg),
    # so candidates are matched on the upper-cased leaf and resolved back to the
    # real property name.
    set have {}
    foreach p [list_property $obj] {
        if {[string match -nocase "CONFIG.*" $p]} {
            dict set have [string toupper [ipcfg::_key_leaf $p]] $p
        }
    }
    set asked {}
    foreach {k v} $d { dict set asked [string toupper [ipcfg::_key_leaf $k]] $v }
    set out {}
    set seen {}
    foreach {k v} $d {
        set leaf [string toupper [ipcfg::_key_leaf $k]]
        # Feature tokens, widest first: the whole leaf; the leaf minus a trailing
        # attribute word (RESET_TYPE -> RESET); and the leading segment after an
        # optional C_ vendor prefix (C_SG_LENGTH_WIDTH -> SG, which is what
        # c_include_sg is named after).
        set toks [list $leaf]
        if {[regexp {^(.+)_(TYPE|MODE|WIDTH|FREQ|FREQUENCY|RATE|POLARITY|VALUE|SEL|SOURCE|SIZE|DEPTH|NUM|COUNT)$} \
                 $leaf -> stem]} {
            lappend toks $stem
        }
        set head [lindex [split [regsub {^C_} $leaf ""] _] 0]
        if {$head ne "" && $head ni $toks} { lappend toks $head }
        foreach t $toks {
            foreach cand [list USE_$t ENABLE_$t EN_$t HAS_$t INCLUDE_$t IS_$t \
                               ${t}_ENABLE ${t}_EN ${t}_USED \
                               C_USE_$t C_ENABLE_$t C_HAS_$t C_IS_$t C_INCLUDE_$t] {
                if {$cand eq $leaf || ![dict exists $have $cand]} { continue }
                set ck [dict get $have $cand]
                if {[dict exists $seen "$leaf>$cand"]} { continue }
                if {[dict exists $asked $cand] &&
                    [ipcfg::_bool [dict get $asked $cand]] eq 1} { continue }
                if {[catch {set cur [get_property $ck $obj]}]} { continue }
                if {[ipcfg::_bool $cur] eq 0} {
                    dict set seen "$leaf>$cand" 1
                    lappend out "INERT:$k:enabler=$ck=$cur"
                }
            }
        }
    }
    return [join $out " "]
}

# --- Intent-side companion: which feature flags does this request need? ---
# check_enablers only fires when an ATTRIBUTE was written, so it cannot catch a
# request whose whole content IS the flag: "expose the locked signal" needs
# CONFIG.USE_LOCKED and names no attribute at all. Pass the behavioural nouns
# from the prompt (reset, locked, interrupt, debug ...) and get back the boolean
# parameters on THIS cell that enable them, with their current values, so a
# still-false flag is visible before you finish rather than after grading.
# Returns "FLAGS:" plus "<word>:<CONFIG.flag>=<value>" per hit, or "FLAGS:none".
proc ipcfg::feature_flags {cell words} {
    if {[catch {set obj [get_bd_cells $cell]}]} { return "FLAGS:none" }
    set params {}
    foreach p [list_property $obj] {
        if {[string match -nocase "CONFIG.*" $p]} { lappend params $p }
    }
    set out {}
    foreach w $words {
        set t [string toupper [string trim $w]]
        if {$t eq ""} { continue }
        foreach p $params {
            set leaf [string toupper [ipcfg::_key_leaf $p]]
            if {![regexp "^(USE|ENABLE|EN|HAS|INCLUDE|IS|C_USE|C_ENABLE|C_HAS|C_IS|C_INCLUDE)_${t}\$" $leaf] &&
                ![regexp "^${t}_(ENABLE|EN|USED|USE)\$" $leaf]} { continue }
            if {[catch {set cur [get_property $p $obj]}]} { continue }
            if {[ipcfg::_bool $cur] eq ""} { continue }
            lappend out "[string tolower $t]:$p=$cur"
        }
    }
    if {![llength $out]} { return "FLAGS:none" }
    return "FLAGS: [join $out " "]"
}

# --- Parse a numeric legal range out of a Vivado error message ---
# Handles the common shapes:
#   "Value '600' is out of the range '50' to '500'"
#   "... out of the range (50 to 500)"
# Returns "{lo hi}" (numbers) or "" when no orderable numeric range is present
# (e.g. an enum list -> caller must ESCALATE, not guess).
proc ipcfg::parse_range {err} {
    set num {-?[0-9.]+(?:[eE][-+]?[0-9]+)?}
    # "range '50' to '500'"  /  "range (50 to 500)"
    if {[regexp "range\[^0-9eE.+-\]*($num)\[^0-9eE.+-\]+to\[^0-9eE.+-\]*($num)" $err -> lo hi]} {
        return [list $lo $hi]
    }
    # "range (1,32)" (comma-separated min,max in parens)
    if {[regexp "range\[^0-9eE.+-\]*\\(($num)\\s*,\\s*($num)\\)" $err -> lo hi]} {
        return [list $lo $hi]
    }
    return ""
}

proc ipcfg::_clamp {want lo hi} {
    if {![ipcfg::_is_num $want] || ![ipcfg::_is_num $lo] || ![ipcfg::_is_num $hi]} { return $want }
    if {double($want) < double($lo)} { return $lo }
    if {double($want) > double($hi)} { return $hi }
    return $want
}

# --- internal: the bare property name (CONFIG.C_GPIO_WIDTH -> C_GPIO_WIDTH) ---
proc ipcfg::_key_leaf {k} { return [regsub {^CONFIG\.} $k ""] }

# --- internal: console lines that mention a key (rich Vivado errors live here) ---
# set_property's catch result is often the generic "failed due to earlier errors";
# the useful "out of the range (1,32)" / "read-only" / "disabled" text is a
# C-level console message. So we accept the captured console and search the lines
# that reference THIS key (by its bare name) for the real reason.
proc ipcfg::_key_lines {k console} {
    set leaf [ipcfg::_key_leaf $k]
    set out {}
    foreach line [split $console "\n"] {
        if {[string first $leaf $line] >= 0} { lappend out $line }
    }
    return [join $out "\n"]
}

# --- Error-driven AUTO-FIX apply (confidence-bounded, console-aware) ---
# Tries the whole -dict fast path first. On failure, isolates per key and applies
# ONLY high-confidence remediations derived from Vivado's OWN feedback. Because
# the rich error is a console message (not the Tcl catch result), pass the
# captured vivado_execute output as `console` so per-key reasons can be read:
#   VALUE_OUT_OF_RANGE -> clamp to the nearest legal bound parsed from the range
#                         (records request->achieved like classify_change RESOLVED)
#   READ_ONLY          -> drop the key (connection/integration-derived; a
#                         set_property can never satisfy it -> confident skip)
#   PARAM_DISABLED     -> if the current (gated) value already equals the request,
#                         OMIT it (already satisfied); otherwise ESCALATE
# Everything we cannot fix with confidence is returned for the agent to ASK the
# user about (PARAM_NOT_FOUND, NOT_SUPPORTED, non-numeric range, disabled-differ,
# unknown errors). Bounded by maxpass per key (default 2) -> no infinite loops.
# Returns one structured line:
#   AUTOFIX:applied={..} clamped={k=>v ..} omitted={..} dropped_readonly={..} ESCALATE={k(reason) ..}
proc ipcfg::autofix_apply {cell d {console ""} {maxpass 2}} {
    set first [ipcfg::apply_dict $cell $d]
    if {[string match "SUCCESS:*" $first]} {
        return "AUTOFIX:applied={all} clamped={} omitted={} dropped_readonly={} ESCALATE={}"
    }
    set applied {}; set clamped {}; set omitted {}; set dropped {}; set escalate {}
    foreach {k v} $d {
        set want $v
        set ok 0
        for {set pass 0} {$pass < $maxpass && !$ok} {incr pass} {
            if {[catch {set_property $k $want [get_bd_cells $cell]} e]} {
                # combine the catch result with the console lines for THIS key
                set ctx "$e\n[ipcfg::_key_lines $k $console]"
                set rng [ipcfg::parse_range $ctx]
                if {$rng ne ""} {
                    lassign $rng lo hi
                    set nv [ipcfg::_clamp $want $lo $hi]
                    if {[ipcfg::_norm $nv] ne [ipcfg::_norm $want]} {
                        lappend clamped "${k}=>${nv}(want=$v)"
                        set want $nv
                        continue
                    }
                    lappend escalate "${k}(range-unfixable)"; break
                } elseif {[string match {*read-only*} $ctx] || [string match {*It is read-only*} $ctx]} {
                    lappend dropped "$k"; set ok 1; break
                } elseif {[string match {*disabled*} $ctx]} {
                    set cur ""
                    catch {set cur [get_property $k [get_bd_cells $cell]]}
                    if {[ipcfg::_norm $cur] eq [ipcfg::_norm $want]} {
                        lappend omitted $k; set ok 1; break
                    }
                    lappend escalate "${k}(disabled-differ:cur=$cur,want=$v)"; break
                } elseif {[string match {*does not exist*} $ctx] || [string match {*not a valid*} $ctx]} {
                    lappend escalate "${k}(not-found)"; break
                } elseif {[string match {*not supported*} $ctx]} {
                    lappend escalate "${k}(not-supported)"; break
                } else {
                    lappend escalate "${k}(error)"; break
                }
            } else {
                lappend applied $k; set ok 1
            }
        }
    }
    return "AUTOFIX:applied={$applied} clamped={$clamped} omitted={$omitted} dropped_readonly={$dropped} ESCALATE={$escalate}"
}

# --- Value-format introspection: read a param back to learn its shape ---
# Use when a key exists but your value is rejected/ignored (e.g. a param that
# expects one comma-separated list string rather than a scalar). Returns the
# current value so the caller can mirror its structure.
proc ipcfg::param_format {cell key} {
    if {[catch {get_property $key [get_bd_cells $cell]} v]} { return "" }
    return $v
}

# --- Baseline snapshot: capture default values BEFORE configuring ---
# Call right after create_cell, passing the keys you are about to set.
# Returns a {key value ...} map you later feed to verify_intent so defaults
# are learned from the IP itself (no per-IP defaults database). For nested
# *_CONFIG keys the whole read-back string is captured.
#   keys: a list of CONFIG.* property names (top-level keys of your dict)
proc ipcfg::snapshot {cell keys} {
    set out {}
    foreach k $keys {
        if {[catch {set v [get_property $k [get_bd_cells $cell]]}]} {
            set v ""
        }
        lappend out $k $v
    }
    return $out
}

# --- Intent audit: catch a wrong-but-valid param that produced NO change ---
# verify_stuck proves a value persisted; verify_intent proves the value is
# observably DIFFERENT from the captured default for requirements that mean
# "enable/select/turn-on". A param whose post-apply value equals its baseline
# default is SUSPECT: you likely set the wrong param for the named feature
# (the right one is still at its default). This fires with NO Vivado error.
#   reqmap: a list of triples {key wantval baselineval ...}
#           - key/wantval come from your dict
#           - baselineval comes from ipcfg::snapshot (the pre-config value)
#   flag_no_change: when 1 (default) a value that equals its default is flagged
#           (suspect-no-change). When 0, only HARD reverts are returned -- use 0
#           once doc grounding confirms the param is correct and the default
#           legitimately satisfies the intent (value_src=default is acceptable;
#           a user not changing a param does not mean the default is wrong).
# Uses classify_change so a value the IP RESOLVED to its nearest-legal neighbor
# (e.g. requested 600 MHz -> achieved 597.20) is NOT flagged as reverted; it is
# a correct application. EXACT and RESOLVED both pass.
# Returns "" if every requirement is observably realized, else a list of
# offending keys tagged (suspect-no-change) or (reverted).
proc ipcfg::verify_intent {cell reqmap {flag_no_change 1}} {
    set bad {}
    foreach {k want base} $reqmap {
        if {[catch {set cur [get_property $k [get_bd_cells $cell]]}]} {
            lappend bad "${k}(missing)"
            continue
        }
        switch -- [ipcfg::classify_change $want $base $cur] {
            EXACT {
                if {[ipcfg::_norm $want] eq [ipcfg::_norm $base] && $flag_no_change} {
                    # reached the value, but it was already the default: no observable
                    # effect -> SOFT flag (re-check doc grounding; value_src=default ok).
                    lappend bad "${k}(suspect-no-change:default=$base)"
                }
            }
            RESOLVED { }
            default  { lappend bad "${k}(reverted:=$cur,want=$want)" }
        }
    }
    return $bad
}

# --- Resolved-aware audit that also REPORTS resolved keys (idea #2) ---
# Like verify_intent but returns a structured triple so coverage can distinguish
# applied-exact from applied-resolved instead of lumping both as "applied".
#   reqmap: {key want base ...}
# Returns "EXACT:{k ...} RESOLVED:{k(=cur,want=w) ...} BAD:{k(...) ...}".
proc ipcfg::audit_intent {cell reqmap} {
    set exact {}; set resolved {}; set bad {}
    foreach {k want base} $reqmap {
        if {[catch {set cur [get_property $k [get_bd_cells $cell]]}]} {
            lappend bad "${k}(missing)"; continue
        }
        switch -- [ipcfg::classify_change $want $base $cur] {
            EXACT    { lappend exact $k }
            RESOLVED { lappend resolved "${k}(=$cur,want=$want)" }
            default  { lappend bad "${k}(reverted:=$cur,want=$want)" }
        }
    }
    return "EXACT:{$exact} RESOLVED:{$resolved} BAD:{$bad}"
}

# --- Disabled/ignored scan: catch gated params that catch{} returns 0 for ---
# In BD mode a gated/disabled parameter is often NOT a hard error: Vivado emits
# a non-fatal warning (e.g. [BD 41-721] / "disabled parameter ... ignored") and
# catch returns 0. Scan the raw vivado_execute output for these patterns so the
# agent can trigger PARAM_DISABLED recovery (find + set the enabling parent).
# Returns "" if none found, else "DISABLED:<matched lines>".
proc ipcfg::find_disabled {output} {
    set hits {}
    foreach line [split $output "\n"] {
        if {[string match {*disabled parameter*} $line] ||
            [string match {*BD 41-721*} $line] ||
            ([string match {*disabled*} $line] && [string match {*ignor*} $line])} {
            lappend hits [string trim $line]
        }
    }
    if {[llength $hits] == 0} { return "" }
    return "DISABLED:[join $hits { | }]"
}

# --- Generic block automation (Designer Assistance) ---
# rule:   xilinx.com:bd_rule:<name> (from doc search; e.g. cips, microblaze,
#         zynq_ultra_ps_e, axi_ethernet, board, mig_7series ...)
# config: optional {param "value" ...} pairs (from doc search)
proc ipcfg::try_automation {cell rule {config {}}} {
    if {[catch {
        if {[llength $config] > 0} {
            apply_bd_automation -rule $rule -config $config [get_bd_cells $cell]
        } else {
            apply_bd_automation -rule $rule [get_bd_cells $cell]
        }
    } e]} {
        return "CONFIGURE_FAIL:AUTOMATION_ERROR:$e"
    }
    return "SUCCESS:automation $rule on $cell"
}

# --- Generic connection-derived driver (replaces per-IP Phase 4 stubs) ---
# Attaches a boundary interface port to a cell's interface pin so that
# elaboration/validation can proceed (and so connection-driven params that
# accept a settable port width can be influenced).
#   pin:  interface pin name on the cell (e.g. S_AXI, S_AXIS_S2MM)
#   vlnv: interface VLNV (e.g. xilinx.com:interface:aximm_rtl:1.0)
#   prop/val: optional property to set on the stub port; tolerated if read-only
# The boundary port mode MIRRORS the pin mode (IPI "make external" rule);
# the caller does NOT pass a mode. If CONFIG.<prop> is read-only on the port
# the width is connection-inherited at integration time -> grade partial.
proc ipcfg::add_stub {cell pin vlnv {prop ""} {val ""}} {
    set sp "STUB_[string map {/ _} $pin]"
    set pinobj [get_bd_intf_pins -quiet $cell/$pin]
    if {$pinobj eq ""} { return "CONFIGURE_FAIL:STUB_ERROR:no intf pin $cell/$pin" }
    set mode [get_property MODE $pinobj]
    if {[catch {
        create_bd_intf_port -mode $mode -vlnv $vlnv $sp
        if {$prop ne ""} {
            catch {set_property CONFIG.$prop $val [get_bd_intf_ports $sp]}
        }
        connect_bd_intf_net [get_bd_intf_ports $sp] $pinobj
    } e]} {
        return "CONFIGURE_FAIL:STUB_ERROR:$e"
    }
    return "SUCCESS:stub ${sp}($mode)->$pin"
}

# --- Cleanup: remove STUB_* ports, delete the cell, restore part if needed ---
proc ipcfg::cleanup {cell {orig_part ""}} {
    variable mode
    if {$mode eq "assemble"} {
        # Persistent build: cells must survive across the assembly. Refuse to
        # delete. (Use ipcfg::set_mode benchmark to re-enable throwaway cleanup.)
        return "SKIP:cleanup disabled in assemble mode (cell $cell kept)"
    }
    foreach p [get_bd_intf_ports -quiet STUB_*] {
        catch {delete_bd_objs [get_bd_intf_nets -quiet -of_objects $p]}
        catch {delete_bd_objs $p}
    }
    foreach p [get_bd_ports -quiet STUB_*] {
        catch {delete_bd_objs [get_bd_nets -quiet -of_objects $p]}
        catch {delete_bd_objs $p}
    }
    if {[llength [get_bd_cells -quiet $cell]] > 0} {
        delete_bd_objs [get_bd_cells $cell]
    }
    if {$orig_part ne "" && [get_property PART [current_project]] ne $orig_part} {
        set bd [ipcfg::_bd_file]
        close_bd_design [current_bd_design]
        set_property PART $orig_part [current_project]
        open_bd_design $bd
    }
    return "SUCCESS:cleanup $cell"
}

# --- Single-call create + configure (perf) ---
# Creates and parameterizes in ONE call via the create_bd_cell -set_param fast
# path, skipping the init-to-default + separate set_property round-trip. Falls
# back to the classic create_cell + apply_dict when -set_param is unavailable on
# this Vivado version or the cell was created but a param failed (so apply_dict
# can classify the real error). IP-agnostic: vlnv/dict are passed in.
proc ipcfg::create_cell_cfg {vlnv cell d} {
    if {[llength [get_bd_cells -quiet $cell]] > 0} {
        return [ipcfg::apply_dict $cell $d]
    }
    if {[llength $d] == 0} { return [ipcfg::create_cell $vlnv $cell] }
    if {![catch {create_bd_cell -type ip -vlnv $vlnv -set_param $d $cell} e]} {
        return "SUCCESS:created+configured $cell (set_param)"
    }
    # Cell may have been created before the param phase failed: classify via apply_dict.
    if {[llength [get_bd_cells -quiet $cell]] > 0} {
        return [ipcfg::apply_dict $cell $d]
    }
    # -set_param unsupported here -> classic two-step path.
    set c [ipcfg::create_cell $vlnv $cell]
    if {[string match "CONFIGURE_FAIL:*" $c]} { return $c }
    return [ipcfg::apply_dict $cell $d]
}

# --- Disabled/gated param reconciliation (simpler than enabler-hunting) ---
# For params reported disabled/gated, decide which are already satisfied instead
# of always pulling them out and re-parameterizing. Compares each key's current
# (gated/read-only) value to the intended value:
#   - equal  -> already satisfied; safe to OMIT (no enabler search needed)
#   - differ -> genuine problem: a real enabler is missing OR the value is wrong
# Only the DIFFER set warrants an enabler doc-search + re-apply.
#   d: the {key want ...} dict you tried to set.
# Returns "OMIT:{k ...} DIFFER:{k(=cur,want=w) ...}"
proc ipcfg::reconcile_disabled {cell d} {
    set omit {}
    set differ {}
    foreach {k v} $d {
        if {[catch {set cur [get_property $k [get_bd_cells $cell]]}]} {
            lappend differ "${k}(missing)"
            continue
        }
        if {[ipcfg::_norm $cur] eq [ipcfg::_norm $v]} {
            lappend omit $k
        } else {
            lappend differ "${k}(=$cur,want=$v)"
        }
    }
    return "OMIT:{$omit} DIFFER:{$differ}"
}

# --- Full-config snapshot (idea #1) ---
# Capture the ENTIRE CONFIG.* dict of a cell in one pass -> {key val ...}.
# Use as a baseline before an apply/automation so config_diff can show every
# key that moved (including IP-driven side effects you did not request).
proc ipcfg::snapshot_all {cell} {
    set obj [get_bd_cells $cell]
    set out {}
    foreach p [list_property $obj] {
        if {[string match "CONFIG.*" $p]} {
            if {![catch {get_property $p $obj} v]} { lappend out $p $v }
        }
    }
    return $out
}

# --- Full-config diff with change classification (idea #1 + #2) ---
# Compare a cell's current full config to a baseline snapshot. Optionally pass a
# {key want ...} request map; requested keys are classified EXACT/RESOLVED/
# REVERTED, every other moved key is reported CHANGED (an IP side effect).
# Returns {key old new class ...}; unrequested+unchanged keys are dropped.
proc ipcfg::config_diff {cell baseline {reqmap {}}} {
    set now [ipcfg::snapshot_all $cell]
    set out {}
    foreach {k new} $now {
        set old  [expr {[dict exists $baseline $k] ? [dict get $baseline $k] : ""}]
        set want [expr {[dict exists $reqmap $k]   ? [dict get $reqmap $k]   : ""}]
        set cls  [ipcfg::classify_change $want $old $new]
        if {$want ne "" || $cls eq "CHANGED"} { lappend out $k $old $new $cls }
    }
    return $out
}

# --- System-intent heuristic (idea #5) ---
# Does the prompt describe a SUBSYSTEM realized through block automation / a
# wizard rather than plain standalone CONFIG.* props (integrated memory
# controllers, a PCIe controller, PS PL-fabric clocks, hardened peripherals)?
# Returns "SYSTEM:{reason ...}" or "STANDALONE". A SYSTEM verdict tells the agent
# to try automation-first and, if no rule exists and the params are gated, to
# report integration-derived honestly rather than fighting disabled CONFIG.
proc ipcfg::is_system_intent {text} {
    set t [string tolower $text]
    set reasons {}
    foreach {label pats} {
        integrated-memory-controller {{memory controller} {integrated ddr} ddr4 ddr5 lpddr interleav}
        pcie-controller              {pcie endpoint {root port} {root complex}}
        ps-fabric-clocks             {{pl clock} {fabric clock} {pl fabric} {processing system}}
        ps-hardened-peripheral       {can-fd canfd {on mio} pmc_mio ps_mio peripheral}
    } {
        foreach p $pats {
            if {[string first $p $t] >= 0} { lappend reasons $label; break }
        }
    }
    if {[llength $reasons] == 0} { return "STANDALONE" }
    return "SYSTEM:$reasons"
}

# --- Automation rule enumeration (idea #5) ---
# The loaded Designer-Assistance rules ARE enumerable via the internal command
#     ::bd::util_cmd rules dump
# which prints a "[DBG] RulesMap:" block mapping
#     "<vlnv-or-intf>":["<description>", "<rule-short-name>", "<rules.tcl path>"]
# The dump is a C-level message (NOT Tcl `puts`/return), so it cannot be captured
# in-proc; the AGENT runs the dump in one execute, reads the RulesMap from the
# output, and feeds that text here (same pattern as find_disabled).
# rule_for_vlnv returns "RULE:xilinx.com:bd_rule:<short> desc={...}" or "RULE:none".
# vlnv may be version-free (xilinx.com:ip:axi_noc2) or full (…:1.1).
proc ipcfg::rule_for_vlnv {dump vlnv} {
    foreach line [split $dump "\n"] {
        set line [string trim $line]
        if {![regexp {^"([^"]+)":\[(.*)\],?$} $line -> key rest]} continue
        if {$key ne $vlnv && ![string match "${vlnv}:*" $key]} continue
        set q [regexp -all -inline {"([^"]*)"} $rest]
        set desc  [lindex $q 1]   ;# 1st quoted = human description
        set short [lindex $q 3]   ;# 2nd quoted = rule short-name
        if {$short ne ""} { return "RULE:xilinx.com:bd_rule:$short desc={$desc}" }
    }
    return "RULE:none"
}

# --- Automation-first apply + HARVEST (idea #5) ---
# Discover the rule with `::bd::util_cmd rules dump` + ipcfg::rule_for_vlnv (rule
# IDs are xilinx.com:bd_rule:<short>). apply_bd_automation is the apply entry point.
# This applies the rule and HARVESTS what it produced: the CONFIG keys that
# changed on the cell (vs a baseline) and any new cells created, so the agent can
# confirm the harvest matches intent instead of guessing gated CONFIG. NOTE a bare
# apply with no -config is often a no-op for subsystem features (e.g. NoC MC needs
# its MC options in <config>); pass the rule's options (from its rules.tcl/docs).
proc ipcfg::apply_automation_harvest {cell rule {config {}} {baseline {}}} {
    set cells_before [get_bd_cells -quiet]
    if {$baseline eq ""} { set baseline [ipcfg::snapshot_all $cell] }
    if {[catch {
        if {[llength $config] > 0} {
            apply_bd_automation -rule $rule -config $config [get_bd_cells $cell]
        } else {
            apply_bd_automation -rule $rule [get_bd_cells $cell]
        }
    } e]} {
        # Classify the common automation failures so the agent knows the NEXT move
        # instead of treating every failure as opaque (learned from the rave2 run):
        #   - missing required option key  -> call automation_config_schema, fill it
        #   - board-preset / part SysMon    -> set BOARD_PART / load preset first
        if {[regexp {key \"([^\"]+)\" not known in dictionary} $e -> miss]} {
            return "CONFIGURE_FAIL:MISSING_AUTOMATION_KEY:$miss (run ipcfg::automation_config_schema <rule_file> to get required keys + defaults, then re-apply with a full -config)"
        }
        if {[regexp -nocase {SMON_MEAS|board.?preset|out of range.*PKG|usr_constraints} $e]} {
            return "CONFIGURE_FAIL:NEEDS_BOARD_PRESET:$e (set_property BOARD_PART / load the board preset before this automation -- see ipiasm::require_board_preset)"
        }
        return "CONFIGURE_FAIL:AUTOMATION_ERROR:$e"
    }
    set changed [ipcfg::config_diff $cell $baseline]
    set new_cells {}
    foreach c [get_bd_cells -quiet] {
        if {[lsearch -exact $cells_before $c] < 0} { lappend new_cells $c }
    }
    return "HARVEST:changed={$changed} new_cells={$new_cells}"
}

# --- Automation rule CONFIG schema discovery (idea: rave2 run) ---
# Block-automation rules (ps_wizard, axi_noc2, visp_ss, cips, ...) REQUIRE an
# options dict; a bare apply or `{}` fails with `key "<k>" not known in dictionary`
# (ps_wizard -> mc_type, visp_ss -> mem_map, ...). Rather than reverse-engineer the
# rule by hand, this reads the rule's own .tcl (path is the 3rd element of the
# `::bd::util_cmd rules dump` RulesMap entry) and returns the option keys apply_rule
# READS plus their default values, so the agent can build a valid -config.
#
# It harvests two things from the rule file:
#   1) keys  = every `dict get <...param_dict|RULE.OPTIONS|opts...> "<key>"`
#   2) defaults = the `config [dict create <k>_none "X" ... noc_def "Y" ...]` literals,
#      resolved through the `set gui_values(<key>) "[dict get $config <cfgkey>]"` map.
# Returns: SCHEMA:keys={k1 k2 ...} defaults={k1 v1 k2 v2 ...} file=<path>
# (defaults are best-effort GUI defaults; combo-only keys with no literal default
#  are reported with value "" so the agent supplies one from intent/docs.)
proc ipcfg::automation_config_schema {rule_file} {
    if {![file exists $rule_file]} { return "SCHEMA_ERR:no rule file $rule_file" }
    set fh [open $rule_file r]; set txt [read $fh]; close $fh
    # Block automations split apply_rule (rule .tcl) and the worker (sibling
    # utils.tcl) -- e.g. ps_wizard reads mc_type in bd.tcl but boot_config/pl_clocks
    # in utils.tcl. Merge both so the key set is complete.
    set utils [file join [file dirname $rule_file] utils.tcl]
    if {[file exists $utils]} { set u [open $utils r]; append txt "\n[read $u]"; close $u }
    # 1) option keys read from the USER options dict. Capture the source var and
    #    whitelist it so we get RULE.OPTIONS aliases (param_dict, config_dict, opts)
    #    but NOT the rule's internal `$config` defaults dict.
    set keys {}
    foreach {full var key} [regexp -all -inline {dict get +\$?\{?([A-Za-z0-9_.]+)\}? +\"?([a-z0-9_]+)\"?} $txt] {
        if {![regexp {^(param_dict|RULE\.OPTIONS|opts|config_dict)$} $var]} continue
        if {[regexp {(_none|_def|_jtag|_yes|_nocpm|_option|_classic|_board)$} $key]} continue
        if {[lsearch -exact {name value value_list parent widgets config} $key] >= 0} continue
        lappend keys $key
    }
    set keys [lsort -unique $keys]
    # 2) literal defaults from the rule's `config` dict (lines like:  <key> "value" \)
    array set cfg {}
    foreach line [split $txt "\n"] {
        if {[regexp {^\s*([a-z0-9_]+)\s+\"([^\"]*)\"\s*\\?\s*$} $line -> k v]} { set cfg($k) $v }
    }
    # gui_values(<optkey>) "[dict get $config <cfgkey>]"  -> map optkey to its default
    array set defmap {}
    foreach m [regexp -all -inline {gui_values\(([a-z_]+)\)\s+\"\[dict get \$config ([a-z_]+)\]\"} $txt] {
        # regexp -all -inline returns full,sub1,sub2 triples
    }
    foreach {full ok ck} [regexp -all -inline {gui_values\(([a-z_]+)\)\s+\"\[dict get \$config ([a-z_]+)\]\"} $txt] {
        if {[info exists cfg($ck)]} { set defmap($ok) $cfg($ck) }
    }
    set defaults {}
    foreach k $keys {
        if {[info exists defmap($k)]} {
            lappend defaults $k $defmap($k)
        } elseif {[info exists cfg(${k}_none)]} {
            lappend defaults $k $cfg(${k}_none)
        } else {
            lappend defaults $k ""
        }
    }
    return "SCHEMA:keys={$keys} defaults={$defaults} file=$rule_file"
}

# --- Coverage report (partial-configuration disclosure, REQUIRED) ---
# Turns the Step 1.5 requirement ledger into a verdict + a list of prompt parts
# that could NOT be parameterized, so the skill always discloses what it failed
# to apply and why.
#   ledger: list of triples {requirement_text key outcome ...} where outcome is
#           applied | default | unapplied:<reason>
# Returns a multi-line report beginning COVERAGE:FULL or COVERAGE:PARTIAL.
#   Outcome vocabulary (per requirement):
#     applied | applied-resolved:<achieved> | default | unapplied:<reason>
#   - applied-resolved means the IP snapped the request to its nearest legal
#     value (config_diff/classify_change -> RESOLVED); it IS applied, just
#     disclosed separately so the request-vs-achieved difference is transparent.
proc ipcfg::coverage_report {ledger} {
    set applied {}
    set resolved {}
    set unapplied {}
    foreach {req key outcome} $ledger {
        set line "  - \"$req\" (param: $key): $outcome"
        if {[string match "unapplied*" $outcome]} {
            lappend unapplied $line
        } elseif {[string match "applied-resolved*" $outcome] || [string match "resolved*" $outcome]} {
            lappend resolved $line
        } else {
            lappend applied $line
        }
    }
    set verdict [expr {[llength $unapplied] == 0 ? "FULL" : "PARTIAL"}]
    set out "COVERAGE:$verdict"
    if {[llength $applied] > 0} {
        append out "\nApplied (exact):\n[join $applied "\n"]"
    }
    if {[llength $resolved] > 0} {
        append out "\nApplied (resolved to nearest legal value):\n[join $resolved "\n"]"
    }
    if {[llength $unapplied] > 0} {
        append out "\nNOT applied (could not parameterize from the prompt):\n[join $unapplied "\n"]"
    }
    return $out
}

# --- Scoped standalone introspection (idea #4): COMPLETE param neighborhood ---
# On a throwaway standalone `create_ip` cell, return the CONFIG.* params whose
# NAME matches a feature keyword (filtered — not a full dump). Use when a feature
# could be split across sibling params so a requirement maps to the COMPLETE set
# rather than the first name-match. Validated: mipi_csi2_rx + "lane" returns BOTH
# CONFIG.CMN_NUM_LANES and CONFIG.C_DPHY_LANES (+ active-lane siblings).
# This is the ONE sanctioned use of list_property (scoped, on a scratch cell).
# Returns "DISCOVER:<param ...>" or "DISCOVER_ERR:<msg>". The scratch IP is deleted.
proc ipcfg::discover_params {vlnv keyword {tmpdir /tmp/ipcfg_disc}} {
    set name "ipcfg_disc_[clock clicks]"
    file mkdir $tmpdir
    if {[catch {create_ip -vlnv $vlnv -module_name $name -dir $tmpdir} e]} {
        # IPI-only IPs (2026.1 ps_wizard: "[Ipptcl 7-1663] ... intended for use
        # in IPI only") can never be created as managed IP, so this scratch-cell
        # path cannot work for them. Name the condition so the caller switches to
        # the BD-cell path rather than retrying a doomed create_ip.
        if {[string match {*IPI only*} $e] || [string match {*7-1663*} $e]} {
            return "DISCOVER_IPI_ONLY:$vlnv (use ipcfg::find_params on a BD cell)"
        }
        return "DISCOVER_ERR:$e"
    }
    # Synonym-broadened: a prompt word ("CAN-FD") rarely equals the parameter
    # spelling ("PS_CAN1_PERIPHERAL"). Stop at the first spelling that hits, so
    # precision is kept while a single-spelling miss no longer returns nothing.
    set hits {}
    foreach pat [ipcfg::_synonyms $keyword] {
        foreach p [list_property [get_ips $name]] {
            if {[string match -nocase "CONFIG.*$pat*" $p]} { lappend hits $p }
        }
        if {[llength $hits]} { break }
    }
    catch {
        remove_files [get_files -quiet $tmpdir/$name/$name.xci]
        file delete -force $tmpdir/$name
    }
    return "DISCOVER:$hits"
}

# ============================================================
# Native IP-Integrator introspection (Vivado 2026.1+, VIVADO-23126)
# VERSION-GATED: every proc degrades cleanly to the 2025.2 reactive path
# (discover_params + doc search + parse_range). Detection is by COMMAND
# PRESENCE, not the version string, because several 2026.1_* build trees report
# 2025.2.0 and lack these commands. Use SURGICALLY: dump_param_deps files are
# large (36 KB axi_gpio .. 172 KB ps_wizard .. 665 KB axi_noc) -- ALWAYS write to
# a file and read only the targeted param block, never inline the whole dump.
# ============================================================

# Detect+cache native capabilities once per session. Returns a dict:
#   version <s> dump_param_deps <0|1> can_connect <0|1>
proc ipcfg::native_caps {} {
    variable _native_caps
    if {[info exists _native_caps]} { return $_native_caps }
    set dpd [expr {[llength [info commands ::debug::dump_param_deps]] > 0}]
    set cc 0
    catch { set h ""; catch {bd::util_cmd -help} h; set cc [string match *can_connect* $h] }
    set ver "unknown"; catch { set ver [version -short] }
    set _native_caps [dict create version $ver dump_param_deps $dpd can_connect $cc]
    return $_native_caps
}
# Convenience gate: ipcfg::has_native dump_param_deps | can_connect -> 0/1
proc ipcfg::has_native {feature} {
    if {[catch {dict get [ipcfg::native_caps] $feature} v]} { return 0 }
    return $v
}

# --- dump_param_deps wrapper: resolved ranges + Enabled/Disabled + dep graph ---
# Writes the (large) dump to a FILE; returns a one-line handle. The agent then
# reads only the param block(s) it needs via ipcfg::param_block. On older Vivado
# returns PARAM_DEPS_NA so the caller falls back to discover_params + doc search.
#   ipname : a managed-IP instance name (make one with create_ip first). BD cell
#            names are NOT accepted by dump_param_deps.
proc ipcfg::param_deps {ipname {file ""}} {
    if {![ipcfg::has_native dump_param_deps]} { return "PARAM_DEPS_NA" }
    # dump_param_deps needs a MANAGED IP instance. Many subsystem IPs are
    # IPI-only and cannot be created with create_ip at all -- on 2026.1
    # `ps_wizard` refuses with "[Ipptcl 7-1663] ... intended for use in IPI
    # only" -- so this whole path is unavailable for them. Say so explicitly
    # instead of surfacing a confusing create_ip/get_ips error: the caller must
    # switch to ipcfg::find_params / ipcfg::cell_dict_keys on the BD cell.
    if {[llength [get_ips -quiet $ipname]] == 0} {
        return "PARAM_DEPS_NO_MANAGED_IP:$ipname (IPI-only IPs cannot be\
created with create_ip -- use ipcfg::find_params on the BD cell instead)"
    }
    if {$file eq ""} { set file /tmp/ipcfg_pd_[string map {/ _ : _} $ipname].txt }
    if {[catch {::debug::dump_param_deps -filename $file $ipname} e]} {
        return "PARAM_DEPS_ERR:$e"
    }
    set sz [expr {[file exists $file] ? [file size $file] : 0}]
    return "PARAM_DEPS:$file:$sz"
}

# --- targeted read: pull ONE param's block (Range/Enabled/Disabled/Default) ---
# Returns just that param's block (token-cheap), never the whole dump. Blocks in
# the dump are separated by lines of asterisks.
proc ipcfg::param_block {file param} {
    if {![file exists $file]} { return "PB_ERR:no file $file" }
    set fh [open $file r]
    set cur {}; set found ""
    while {[gets $fh ln] >= 0} {
        if {[regexp {^\*{5,}} $ln]} {
            set txt [join $cur "\n"]
            if {[regexp -line "^Parameter Name:\\s+$param\\s*$" $txt]} { set found $txt; break }
            set cur {}
        } else {
            lappend cur $ln
        }
    }
    if {$found eq ""} {
        set txt [join $cur "\n"]
        if {[regexp -line "^Parameter Name:\\s+$param\\s*$" $txt]} { set found $txt }
    }
    close $fh
    if {$found eq ""} { return "PB_MISS:$param" }
    return [string trim $found]
}

# --- nested-dict introspection (PS/CIPS-class subsystem IPs) ---
# dump_param_deps emits per-param Range/Enabled/Disabled metadata only for
# TOP-LEVEL params. Subsystem IPs carry the real sub-keys inside ONE resolved
# dict value (ps_wizard PS11_CONFIG_INTERNAL = a ~1315-key flat Tcl dict;
# versal_cips PS_PMC_CONFIG/CPM_CONFIG similarly). This recovers sub-key NAMES +
# CURRENT/DEFAULT VALUES (no doc search needed); per-sub-key valid-range and
# gating are still NOT provided here -> use doc / set-and-observe for those.
#   dictparam : the param whose Current Value is a dict (e.g. PS11_CONFIG_INTERNAL).
#   subkey    : "" -> list all top-level sub-keys; else -> that sub-key's value.
proc ipcfg::param_dict {file dictparam {subkey ""}} {
    set blk [ipcfg::param_block $file $dictparam]
    if {[string match "PB_*" $blk]} { return $blk }
    if {![regexp -line {^Current Value:(.*)$} $blk -> val]} { return "PD_ERR:no current value" }
    set val [string trim $val]
    if {$val eq "" || ![string is list $val] || [llength $val] % 2 != 0} {
        return "PD_ERR:value not a dict (len=[string length $val])"
    }
    if {$subkey eq ""} { return "PD_KEYS:[dict keys $val]" }
    if {[dict exists $val $subkey]} { return "PD:$subkey=[dict get $val $subkey]" }
    return "PD_MISS:$subkey"
}

# --- per-sub-key RANGE via set-and-observe (the gap dump_param_deps can't fill) ---
# PROVEN on 2026.1_released ps_wizard: dump_param_deps gives sub-key NAMES+VALUES but
# NO sub-key range. The IP customizer still KNOWS the range and reports it on a failed
# set (IPLEVEL_DRC_PROC), e.g.:
#   PARAM PS_USE_PMCPL_CLK0 with value <7> is out of range  { 0,1 }
# So we push an out-of-range sentinel for ONE sub-key and parse the message. The
# customizer auto-restores to the previous valid config on error, so this is
# NON-DESTRUCTIVE. Version-INDEPENDENT (works on 2025.2 too -- it is the customizer
# feedback path, not a VIVADO-23126 command), so it is the range fallback on BOTH
# versions. Operates on a BD CELL (the dict user-param, e.g. PS11_CONFIG -- NOT the
# *_INTERNAL, which is derived/read-only).
# CAVEAT (also proven): only USER-FACING sub-keys are range-checked. Derived keys
# (PMC_CRP_*_DIVISOR0/SRCSEL/ACT_FREQMHZ ...) accept anything and get recomputed by
# the resolver -> they have no user range (returns PSR_NOTVALIDATED).
#   cell      : BD cell name (e.g. ps_wiz)
#   dictparam : the dict USER-param (e.g. PS11_CONFIG)
#   subkey    : sub-key to probe (e.g. PS_USE_PMCPL_CLK0)
#   sentinel  : an out-of-range value (default 999999; use a clearly-illegal token)
#   IMPORTANT (proven on 2026.1): the legal-set text ("...is out of range { 0,1 }")
#   is emitted to the Vivado MESSAGE LOG, NOT into the Tcl catch result or $::errorInfo,
#   and the log is not flushed synchronously enough to read in-proc. So run this with
#   vivado_execute capture_log=true: the SAME response carries both this proc's status
#   line AND the range line, which you parse with ipcfg::range_from_log (or read the
#   "is out of range { ... }" line directly). One MCP round-trip, non-destructive.
proc ipcfg::probe_subkey_range {cell dictparam subkey {sentinel 999999}} {
    set c [get_bd_cells -quiet $cell]
    if {$c eq ""} { return "PSR_ERR:no cell $cell" }
    set prop CONFIG.$dictparam
    set ov ""; catch { set ov [get_property -quiet $prop $c] }
    if {[string is list $ov] && [llength $ov] % 2 == 0} {
        set try $ov; dict set try $subkey $sentinel
    } else {
        set try [list $subkey $sentinel]
    }
    set rc [catch { set_property $prop $try $c } e]
    if {$rc != 0} {
        # validated key: customizer rejected the sentinel and AUTO-RESTORED the cell
        # (non-destructive). The legal set is in the captured log -> range_from_log.
        return "PSR_OUT_OF_RANGE:$subkey (range is in the captured log: 'PARAM $subkey ... is out of range { ... }')"
    }
    # rc==0: sentinel was accepted. Distinguish a live-but-unchecked user input from a
    # key the customizer ignored/derived (not retained in the override dict).
    set kept 0
    catch {
        set now [get_property -quiet $prop $c]
        if {[string is list $now] && [llength $now] % 2 == 0 && [dict exists $now $subkey] && [dict get $now $subkey] eq $sentinel} { set kept 1 }
    }
    catch { set_property $prop $ov $c }   ;# restore prior override
    if {$kept} { return "PSR_NOTVALIDATED:$subkey (input accepted; no user range enforced)" }
    return "PSR_NOKEY:$subkey (ignored or derived -- not a user-settable input)"
}

# --- stateless parser: pull a sub-key's legal range out of a captured console ---
# Pair with probe_subkey_range run under capture_log=true. Returns
# RANGE:<subkey>={ ... } | RANGE_NONE:<subkey>.
proc ipcfg::range_from_log {console subkey} {
    foreach line [split $console "\n"] {
        if {[string first "is out of range" $line] < 0} continue
        if {[string first $subkey $line] < 0} continue
        if {[regexp {is out of range\s*\{([^\}]*)\}} $line -> rng]} {
            return "RANGE:$subkey={[string trim $rng]}"
        }
    }
    return "RANGE_NONE:$subkey"
}

# --- GATING/derivation via set-and-observe: apply legal inputs, read resolved dict ---
# PROVEN on 2026.1_released: requesting {PS_USE_PMCPL_CLK0 1 PMC_CRP_PL0_REF_CTRL_FREQMHZ 250}
# made the customizer derive ACT_FREQMHZ=249.997 DIVISOR0=4 SRCSEL=NPLL PS_PMCPL_CLK0_BUF=1.
# So the resolved *_INTERNAL dict IS the gating/derivation result. Use this to learn
# which sub-keys a given input gates/derives. Version-INDEPENDENT.
# NOTE: this APPLIES the override (it is a real config change, by design -- it is how
# you actually configure the IP). Pass only legal inputs. Snapshot CONFIG.<userparam>
# yourself first if you need to roll back.
#   cell          : BD cell name
#   userparam     : the dict USER-param you set (e.g. PS11_CONFIG)
#   override      : a Tcl dict of legal {subkey value ...} inputs to apply
#   internalparam : resolved/derived dict param (default <userparam>_INTERNAL)
#   wantkeys      : "" -> just report resolved key count; else list -> return those keys' values
proc ipcfg::resolve_subkeys {cell userparam override {internalparam ""} {wantkeys ""}} {
    set c [get_bd_cells -quiet $cell]
    if {$c eq ""} { return "RSK_ERR:no cell $cell" }
    if {$internalparam eq ""} { set internalparam ${userparam}_INTERNAL }
    if {[catch { set_property CONFIG.$userparam $override $c } e]} {
        return "RSK_FAIL:[string range $e 0 200]"
    }
    set iv ""; catch { set iv [get_property -quiet CONFIG.$internalparam $c] }
    if {![string is list $iv] || [llength $iv] % 2 != 0} { return "RSK_ERR:$internalparam not a dict" }
    if {$wantkeys eq ""} { return "RSK_KEYS:[llength [dict keys $iv]] resolved sub-keys" }
    set out {}
    foreach k $wantkeys {
        if {[dict exists $iv $k]} { lappend out $k [dict get $iv $k] } else { lappend out $k <absent> }
    }
    return "RSK:$out"
}

# ============================================================
# Deterministic front door: discovery -> apply -> verify in ONE call
#
# Everything above is a primitive the agent composes by hand, and that is where
# run-to-run variance came from. On an observed 2026.1 run the agent used NONE
# of the discovery helpers: it hand-rolled get_property + lsearch, searched for
# "CANFD" (zero hits, because the params are PS_CAN*), broadened by hand, and
# had already written a guessed nested shape before it knew the real key names.
# Same prompt, different path each time.
#
# The procs below move that sequence into code: the agent supplies INTENT, the
# library supplies the PROCEDURE. A step that isn't a model decision can't vary.
# ============================================================

# --- keyword synonym expansion (pure string work, no MCP round-trips) ---
# A prompt's feature word rarely equals the parameter spelling: "CAN-FD" has to
# reach PS_CAN1_PERIPHERAL. Matching runs against an already-fetched key list,
# so trying many spellings costs nothing. Ordered most- to least-specific, and
# callers stop at the first spelling that hits, which keeps precision.
# Progressive truncation of the compact form is what bridges the gap generically
# (CANFD -> CANF -> CAN); *minlen* floors it (2 for catalog family search).
proc ipcfg::_synonyms {keyword {minlen 3}} {
    set k [string toupper [string trim $keyword]]
    set alnum [regsub -all {[^A-Za-z0-9]} $k ""]
    set under [regsub -all {[^A-Za-z0-9]+} $k "_"]
    set out {}
    foreach c [list $k $under $alnum] {
        if {$c ne "" && $c ni $out} { lappend out $c }
    }
    for {set n [expr {[string length $alnum] - 1}]} {$n >= $minlen} {incr n -1} {
        set c [string range $alnum 0 [expr {$n - 1}]]
        if {$c ni $out} { lappend out $c }
    }
    return $out
}

# --- internal: read a property whose value is a Tcl dict ("" when it isn't) ---
proc ipcfg::_dict_val {obj prop} {
    set v ""
    if {[catch {set v [get_property -quiet $prop $obj]}]} { return "" }
    if {$v eq ""} { return "" }
    if {![string is list $v] || [llength $v] % 2 != 0} { return "" }
    return $v
}

# --- nested-dict introspection straight off a BD CELL (no create_ip, no dump) ---
# The documented native path (param_deps -> param_dict) needs a MANAGED IP
# instance, but subsystem IPs are often IPI-only: on 2026.1 `ps_wizard` reports
# "[Ipptcl 7-1663] ... intended for use in IPI only", so create_ip cannot be
# used and that path is simply unavailable. The live BD cell carries the whole
# dict anyway, so read it there -- one round-trip, no 172 KB file.
#   dictparam : dict-valued param, with or without the CONFIG. prefix. Falls
#               back to <param>_INTERNAL, where the RESOLVED sub-keys live when
#               the user-facing param is still empty.
#   pattern   : "" -> every sub-key; else a keyword, synonym-broadened.
# Returns:
#   CDK:<prop> pattern=<matched> n=<count> {k v k v ...}
#   CDK_NONE:<prop> (nothing matched any spelling)
#   CDK_ERR:<detail>
proc ipcfg::cell_dict_keys {cell dictparam {pattern ""}} {
    set c [get_bd_cells -quiet $cell]
    if {$c eq ""} { return "CDK_ERR:no cell $cell" }
    set base [regsub {^CONFIG\.} $dictparam ""]
    set d ""; set prop ""
    foreach cand [list CONFIG.$base CONFIG.${base}_INTERNAL] {
        set d [ipcfg::_dict_val $c $cand]
        if {$d ne ""} { set prop $cand; break }
    }
    if {$d eq ""} { return "CDK_ERR:$dictparam is not a populated dict on $cell" }
    if {$pattern eq ""} {
        return "CDK:$prop pattern=* n=[expr {[llength $d]/2}] $d"
    }
    foreach pat [ipcfg::_synonyms $pattern] {
        set hits {}
        foreach {k v} $d {
            if {[string match -nocase "*$pat*" $k]} { lappend hits $k $v }
        }
        if {[llength $hits]} {
            return "CDK:$prop pattern=$pat n=[expr {[llength $hits]/2}] $hits"
        }
    }
    return "CDK_NONE:$prop (no sub-key matches [ipcfg::_synonyms $pattern])"
}

# --- unified feature discovery on a BD cell: flat params AND nested sub-keys ---
# Answers the two questions that drive every configure in one call: what are the
# real parameter names for this feature, and what SHAPE do they take (flat
# CONFIG props vs sub-keys of a dict container). Both are read off the live cell,
# so it is version-agnostic by construction: the same call finds flat
# CONFIG.PS_CAN1_PERIPHERAL on a 2025.2 `ps11` and the nested
# CONFIG.PS11_CONFIG/PS_CAN1_PERIPHERAL on a 2026.1 `ps_wizard`.
# Flat params are preferred when both exist -- they are directly settable.
# Returns:
#   FP:FLAT pattern=<p> n=<k> {CONFIG.k ...}
#   FP:NESTED container=CONFIG.<X> pattern=<p> n=<k> {sub ...}
#   FP_NONE:<detail> | FP_ERR:<detail>
proc ipcfg::find_params {cell keyword} {
    set c [get_bd_cells -quiet $cell]
    if {$c eq ""} { return "FP_ERR:no cell $cell" }
    set props {}
    foreach p [list_property $c] {
        if {[string match "CONFIG.*" $p]} { lappend props $p }
    }
    foreach pat [ipcfg::_synonyms $keyword] {
        set hits {}
        foreach p $props {
            if {[string match -nocase "*$pat*" $p]} { lappend hits $p }
        }
        if {[llength $hits]} {
            return "FP:FLAT pattern=$pat n=[llength $hits] {$hits}"
        }
    }
    foreach p $props {
        if {[ipcfg::_dict_val $c $p] eq ""} { continue }
        set r [ipcfg::cell_dict_keys $cell $p $keyword]
        if {![string match "CDK:*" $r]} { continue }
        set pat ""
        regexp {pattern=(\S+)} $r -> pat
        set subs {}
        foreach {k v} [lrange $r 3 end] { lappend subs $k }
        # Report the USER-settable container, never the derived *_INTERNAL.
        set container [regsub {_INTERNAL$} $p ""]
        return "FP:NESTED container=$container pattern=$pat n=[llength $subs] {$subs}"
    }
    return "FP_NONE:nothing matches '[join [ipcfg::_synonyms $keyword] ,]' on $cell"
}

# --- catalog-grounded IP identity (IP names change between releases) ---
# `vlnv_ok` only validates a VLNV you already picked, so it cannot rescue a name
# that no longer exists. On 2026.1 `xilinx.com:ip:ps11:1.0` is absent from the
# catalog entirely (the PS family is ps11_vip / ps_wizard / psx_vip /
# psx_wizard), so a 2025.2-era name fails with nothing to correct it. Resolve
# against the live catalog instead of trusting documentation.
# Returns:
#   VLNV:<vendor:lib:name:ver>     exact hit (highest version)
#   VLNV_CANDIDATES:{<vlnv> ...}   no exact hit; what this release ships instead
#   VLNV_NONE:<hint>
proc ipcfg::resolve_vlnv {hint} {
    set h [string trim $hint]
    set name $h
    if {[string first : $h] >= 0} {
        set parts [split $h :]
        if {[llength $parts] >= 3} { set name [lindex $parts 2] }
    }
    set exact [get_ipdefs -quiet *:${name}:*]
    if {[llength $exact]} { return "VLNV:[lindex [lsort $exact] end]" }
    # Offer catalog neighbours so the choice is grounded in what this release
    # actually ships. minlen 2 so a stale "ps11" still surfaces the PS family.
    # Accumulate across ALL spellings rather than stopping at the first hit:
    # "ps11" matches ps11_vip on its most specific spelling, but the IP the
    # caller actually wants (ps_wizard) only appears under the broader "PS", and
    # an identity search must show the alternatives, not the first near-miss.
    set all [get_ipdefs -quiet]
    set cands {}
    foreach pat [ipcfg::_synonyms $name 2] {
        foreach d [lsort $all] {
            set n [lindex [split $d :] 2]
            if {[string match -nocase "*$pat*" $n] && $d ni $cands} { lappend cands $d }
        }
    }
    if {[llength $cands]} { return "VLNV_CANDIDATES:{$cands}" }
    return "VLNV_NONE:$hint"
}

# --- internal: map a caller's (possibly partial) key onto a discovered name ---
# Exact match first, then a UNIQUE containment match. Ambiguity is never
# guessed: "CAN1" matches both PS_CAN1_CLK and PS_CAN1_PERIPHERAL, and picking
# one would be exactly the coin-flip this whole path exists to remove. Returns
# the name, "" when nothing matched, or AMBIGUOUS:{candidates} so the caller can
# report which precise key to use.
proc ipcfg::_best_name {want names} {
    set w [string toupper [regsub {^CONFIG\.} [string trim $want] ""]]
    foreach n $names {
        if {[string toupper [regsub {^CONFIG\.} $n ""]] eq $w} { return $n }
    }
    set hits {}
    foreach n $names {
        set bare [string toupper [regsub {^CONFIG\.} $n ""]]
        if {[string first $w $bare] >= 0 || [string first $bare $w] >= 0} {
            lappend hits $n
        }
    }
    if {[llength $hits] == 1} { return [lindex $hits 0] }
    if {[llength $hits] > 1}  { return "AMBIGUOUS:{$hits}" }
    return ""
}

# --- THE front door: identity -> discovery -> apply -> verify, in one call ---
# The agent supplies INTENT; this supplies the PROCEDURE. Every step that used
# to be a per-run model decision is fixed here: which discovery command, in what
# order, whether to discover BEFORE writing (always), how to shape a nested
# dict, and what to verify afterwards.
#
#   cell    : BD cell name (created when absent)
#   vlnv    : IP VLNV or bare name; resolved against the catalog first
#   feature : the prompt's feature word (e.g. "CAN-FD"); synonym-broadened
#   intent  : {param-or-subkey value ...}. Keys may be partial or use the
#             prompt's spelling -- each is matched against the DISCOVERED names,
#             so the caller never needs this release's exact spelling.
#
# Returns ONE line:
#   CF:OK shape=<FLAT|NESTED> vlnv=<v> src=<discovery|cache> applied={k v ...}
#   CF:PARTIAL shape=... applied={...} unresolved={...} bad={...} inert={...}
#   CF:FAIL:<TYPE>:<detail>
# `inert` is non-empty when a value persisted but its enabling flag is still off
# (see check_enablers): set the flag and re-apply, or the feature is not there.
proc ipcfg::configure_feature {cell vlnv feature intent} {
    # -- Phase 1: identity from the catalog, not from documentation ----------
    set r [ipcfg::resolve_vlnv $vlnv]
    if {[string match "VLNV_CANDIDATES:*" $r]} {
        return "CF:FAIL:WRONG_IP_NAME:'$vlnv' is not in this release's catalog;\
this release ships [string range $r 16 end]"
    }
    if {[string match "VLNV_NONE:*" $r]} {
        return "CF:FAIL:WRONG_IP_NAME:'$vlnv' not in catalog, no near match"
    }
    set real [string range $r 5 end]
    set ipname [lindex [split $real :] 2]

    # -- Phase 1b: part gate, BEFORE the create ------------------------------
    # An unsupported part is not recoverable from the create error: catch sees
    # only "[Common 17-39] 'create_bd_cell' failed due to earlier errors" while
    # the [BD 5-683] naming the real cause goes to the log. Predict it from the
    # ipdef instead and report the parts that WOULD work, so the caller can make
    # the swap decision with the facts.
    # Explicit part => a confirmation of the identity the CALLER chose, so the
    # shortlist advisory is suppressed: selecting between candidates is the
    # caller's Step 0a' gate, which runs before this and cannot be done here.
    set av [ipcfg::ip_availability [list $ipname] [get_property PART [current_project]]]
    if {[string match "*=WRONG_PART:*" $av]} {
        return "CF:FAIL:WRONG_PART:[string range $av 9 end] -- consider a guarded\
ipcfg::ensure_part; do NOT substitute a different IP that happens to be available"
    }

    # -- Phase 2: the cell must exist before it can be introspected ----------
    set c [ipcfg::create_cell $real $cell]
    if {[string match "CONFIGURE_FAIL:*" $c]} {
        return "CF:FAIL:[string range $c 15 end]"
    }

    # -- Phase 3: DISCOVER before writing anything --------------------------
    # Consult the learned cache first (0 extra work on a hit), but only trust it
    # after a cheap existence re-verify against this cell.
    set shape ""; set container ""; set names {}; set src "discovery"
    set hit [ipcfg::cache_get $ipname $feature]
    if {$hit ne ""} {
        set cs ""; set cp ""
        regexp {"shape"\s*:\s*"([^"]*)"} $hit -> cs
        regexp {"param"\s*:\s*"([^"]*)"} $hit -> cp
        if {$cs ne "" && $cp ne ""} {
            if {$cs eq "FLAT"} {
                set probe $cp
                if {![string match "CONFIG.*" $probe]} { set probe CONFIG.$probe }
                if {![catch {get_property $probe [get_bd_cells $cell]}]} {
                    set shape FLAT; set names [list $probe]; set src "cache"
                }
            } else {
                set cdk [ipcfg::cell_dict_keys $cell $cp $feature]
                if {[string match "CDK:*" $cdk]} {
                    set shape NESTED
                    set container [regsub {_INTERNAL$} [lindex $cdk 0] ""]
                    set container [regsub {^CDK:} $container ""]
                    foreach {k v} [lrange $cdk 3 end] { lappend names $k }
                    set src "cache"
                }
            }
        }
    }
    if {$shape eq ""} {
        set fp [ipcfg::find_params $cell $feature]
        if {[string match "FP_*" $fp]} { return "CF:FAIL:PARAM_NOT_FOUND:$fp" }
        set shape [lindex [split [lindex $fp 0] :] 1]
        if {$shape eq "FLAT"} {
            set names [lindex $fp 3]
        } else {
            set container [string range [lindex $fp 1] 10 end]
            set names [lindex $fp 4]
        }
    }

    # -- Phase 4: map intent onto the DISCOVERED names ----------------------
    set resolved {}
    set unresolved {}
    foreach {want val} $intent {
        set n [ipcfg::_best_name $want $names]
        if {[string match "AMBIGUOUS:*" $n]} {
            lappend unresolved "${want}(ambiguous:[string range $n 10 end])"
        } elseif {$n eq ""} {
            lappend unresolved "${want}(no-match)"
        } else {
            lappend resolved $n $val
        }
    }
    if {[llength $resolved] == 0} {
        return "CF:FAIL:PARAM_NOT_FOUND:unresolved={$unresolved}\
discovered={$names}"
    }

    # -- Phase 5: build the correctly-shaped dict and apply -----------------
    if {$shape eq "FLAT"} {
        set d {}
        foreach {n v} $resolved {
            if {![string match "CONFIG.*" $n]} { set n CONFIG.$n }
            lappend d $n $v
        }
    } else {
        set sub {}
        foreach {n v} $resolved { lappend sub [regsub {^CONFIG\.} $n ""] $v }
        set d [list $container $sub]
    }
    set ap [ipcfg::apply_dict $cell $d]
    if {[string match "CONFIGURE_FAIL:*" $ap]} {
        return "CF:FAIL:[string range $ap 15 end]"
    }

    # -- Phase 6: verify it actually stuck, and that it is not INERT ---------
    # A gated attribute persists and reads back while doing nothing at all, so
    # verify_stuck alone cannot certify the feature was delivered.
    set bad [ipcfg::verify_stuck $cell $d]
    set inert [ipcfg::check_enablers $cell $d]

    # -- Phase 7: write back what was learned (blind-safe: facts, not values) -
    set ipver [lindex [split $real :] 3]
    set learned [expr {$shape eq "FLAT" ? [lindex $resolved 0] : $container}]
    catch {
        ipcfg::cache_put $ipname $feature $learned $shape "" "USER" \
            "cell-introspection" $ipver
    }

    if {[llength $unresolved] || [llength $bad] || $inert ne ""} {
        return "CF:PARTIAL shape=$shape vlnv=$real src=$src applied={$d}\
unresolved={$unresolved} bad={$bad} inert={$inert}"
    }
    return "CF:OK shape=$shape vlnv=$real src=$src applied={$d} verified=all"
}

# --- Learned-config cache (idea #3): consult-first / write-back ---
# Stores earned DISCOVERY facts only (param/shape/enabler/value_src/doc/version),
# never expected values, so it is blind-safe. Shells out to ipcfg_cache.py.
#   cache_get <ip> <feature>            -> JSON entry string, or "" on miss
#   cache_put <ip> <feature> <param> <shape> <enabler> <value_src> <doc> <ipver>
# Flow: consult cache first (0 MCP calls) -> if hit, a cheap get_property
# existence re-verify -> apply; on miss, fall through to doc search; on success,
# write back so the next run is cheaper and deterministic.
proc ipcfg::cache_get {ip feature} {
    variable cache_engine
    variable cache_file
    if {[catch {exec python3 $cache_engine get $cache_file $ip $feature} out]} { return "" }
    return [string trim $out]
}
proc ipcfg::cache_put {ip feature param shape enabler value_src doc ipver} {
    variable cache_engine
    variable cache_file
    if {[catch {exec python3 $cache_engine put $cache_file $ip $feature $param $shape $enabler $value_src $doc $ipver} out]} {
        return "CACHE_ERR:$out"
    }
    return [string trim $out]
}
proc ipcfg::cache_dump {} {
    variable cache_engine
    variable cache_file
    if {[catch {exec python3 $cache_engine dump $cache_file} out]} { return "{}" }
    return $out
}

puts "ipcfg loaded: [info procs ::ipcfg::*]"
