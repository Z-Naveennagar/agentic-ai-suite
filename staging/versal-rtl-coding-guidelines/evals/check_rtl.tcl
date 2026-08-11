# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# Run after synthesis. This script emits structural evidence and raw reports; it does not
# convert report text into a functional pass/fail result.
set rd vivado_agentic_ai_reports/versal-rtl-coding-guidelines/evals
file mkdir $rd
set bram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == BRAM}]
set uram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == URAM}]
set dsp  [get_cells -hier -filter {PRIMITIVE_GROUP == ARITHMETIC && PRIMITIVE_SUBGROUP == DSP}]
set lut  [get_cells -hier -filter {PRIMITIVE_SUBGROUP == LUTRAM}]
set lat  [get_cells -hier -filter {PRIMITIVE_GROUP == REGISTER && PRIMITIVE_SUBGROUP == LATCH}]
set asr  [get_cells -hier -filter {ASYNC_REG == TRUE}]
set dt   [get_cells -hier -filter {DONT_TOUCH == TRUE}]
puts "STRUCTURE BRAM=[llength $bram] URAM=[llength $uram] DSP=[llength $dsp] LUTRAM=[llength $lut] LATCH=[llength $lat] ASYNC_REG=[llength $asr] DONT_TOUCH=[llength $dt]"
report_cdc -details -file $rd/cdc.rpt
report_exceptions -coverage -file $rd/exceptions_coverage.rpt
report_methodology -file $rd/methodology.rpt
report_control_sets -file $rd/control_sets.rpt
