## probe_mem_props.tcl - confirm Versal BRAM/URAM property + output-pin names.
## source in an open design, then: probe_mem_props
proc probe_mem_props {} {
    set bram [lindex [get_cells -hier -quiet -filter {REF_NAME =~ RAMB*}] 0]
    set uram [lindex [get_cells -hier -quiet -filter {REF_NAME =~ URAM288*}] 0]
    foreach {tag cell} [list BRAM $bram URAM $uram] {
        puts "==================== $tag sample: $cell ===================="
        if {$cell eq ""} { puts "  (none found)"; continue }
        puts "  REF_NAME = [get_property REF_NAME $cell]"
        puts "  -- properties matching REG|OREG|CASCADE|DOUT_REG|SELF --"
        foreach pr [lsort [list_property $cell]] {
            if {[regexp {REG|CASCADE|SELF|OREG} $pr]} {
                puts [format "    %-22s = %s" $pr [get_property -quiet $pr $cell]]
            }
        }
        puts "  -- OUT data pins (first 12, non-CAS) --"
        set op [get_pins -quiet -of $cell -filter {DIRECTION == OUT}]
        set n 0
        foreach p $op {
            set rp [get_property REF_PIN_NAME $p]
            if {[regexp {^CAS} $rp]} { continue }
            puts "    $rp"
            incr n; if {$n >= 12} break
        }
    }
}
