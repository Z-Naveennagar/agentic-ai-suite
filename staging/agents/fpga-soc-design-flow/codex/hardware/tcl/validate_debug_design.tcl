# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

# Validate the design-time hardware-validation instrumentation in an open
# implemented design and emit the matching probes file.
#
# Usage:
#   source hardware/tcl/validate_debug_design.tcl
#   hwv_validate_debug_design <absolute-output-path>/debug_nets.ltx

proc hwv_validate_debug_design {ltx_path} {
    set debug_cores [get_debug_cores -quiet]
    set vio_cells [get_cells -hierarchical -quiet -filter {REF_NAME =~ *vio* || ORIG_REF_NAME =~ *vio*}]
    set ila_cells [get_cells -hierarchical -quiet -filter {REF_NAME =~ *ila* || ORIG_REF_NAME =~ *ila*}]

    if {[llength $debug_cores] == 0} {
        error "HWV-DEBUG-1: implemented design contains no debug cores"
    }
    if {[llength $vio_cells] == 0} {
        error "HWV-DEBUG-2: implemented design contains no VIO core"
    }
    if {[llength $ila_cells] == 0} {
        error "HWV-DEBUG-3: implemented design contains no ILA/System ILA core"
    }

    write_debug_probes -force $ltx_path
    if {![file isfile $ltx_path]} {
        error "HWV-DEBUG-4: write_debug_probes did not create $ltx_path"
    }

    return [dict create \
        debug_cores $debug_cores \
        vio_cell_count [llength $vio_cells] \
        ila_cell_count [llength $ila_cells] \
        probes_file [file normalize $ltx_path]]
}
