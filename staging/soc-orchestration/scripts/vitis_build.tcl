#!/usr/bin/env xsct
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# vitis_build.tcl — End-to-end embedded firmware build for PS+PL designs
#
# Uses hsi (Hardware Software Interface) for BSP generation — works reliably
# on headless servers without Eclipse/Vitis IDE backend.
#
# Flow: .xsa → hsi generate_bsp → make BSP → compile app → link .elf
#
# Usage:
#   xsct vitis_build.tcl <xsa_path> <app_src_dir> <build_dir> [options]
#
# Options:
#   -os <standalone|freertos>     OS type (default: standalone)
#   -proc <processor_instance>    Processor (default: psu_cortexa53_0)
#   -app-name <name>              Application name (default: ps_app)

proc usage {} {
    puts "Usage: xsct vitis_build.tcl <xsa_path> <app_src_dir> <build_dir> \[options\]"
    puts "  -os <standalone|freertos>  (default: standalone)"
    puts "  -proc <processor>          (default: psu_cortexa53_0)"
    puts "  -app-name <name>           (default: ps_app)"
    exit 1
}

if {[llength $argv] < 3} { usage }

set xsa_path    [lindex $argv 0]
set app_src_dir [lindex $argv 1]
set build_dir   [lindex $argv 2]

set os_type    "standalone"
set proc_inst  "psu_cortexa53_0"
set app_name   "ps_app"

for {set i 3} {$i < [llength $argv]} {incr i} {
    set arg [lindex $argv $i]
    switch -- $arg {
        -os       { incr i; set os_type   [lindex $argv $i] }
        -proc     { incr i; set proc_inst [lindex $argv $i] }
        -app-name { incr i; set app_name  [lindex $argv $i] }
        default   { puts "Unknown option: $arg"; usage }
    }
}

set xsa_path    [file normalize $xsa_path]
set app_src_dir [file normalize $app_src_dir]
set build_dir   [file normalize $build_dir]

if {![file exists $xsa_path]} {
    puts "ERROR: XSA not found: $xsa_path"
    exit 1
}
if {![file isdirectory $app_src_dir]} {
    puts "ERROR: Source directory not found: $app_src_dir"
    exit 1
}

set bsp_dir   "$build_dir/bsp"
set app_dir   "$build_dir/app"

puts "============================================"
puts "Vitis Embedded Build (hsi-based)"
puts "  XSA:       $xsa_path"
puts "  Sources:   $app_src_dir"
puts "  Build dir: $build_dir"
puts "  OS:        $os_type"
puts "  Processor: $proc_inst"
puts "  App:       $app_name"
puts "============================================"

if {[file exists $build_dir]} {
    puts "Cleaning previous build: $build_dir"
    file delete -force $build_dir
}
file mkdir $build_dir
file mkdir $app_dir

# ---- Step 1: Generate BSP using hsi ----
puts "\n--- Step 1: Generate BSP from XSA ---"
hsi::open_hw_design $xsa_path

set procs [hsi::get_cells -filter {IP_TYPE==PROCESSOR}]
puts "Available processors: $procs"

set pl_ips [hsi::get_cells -filter {IS_PL==true}]
puts "PL peripherals: $pl_ips"

hsi::generate_bsp -os $os_type -proc $proc_inst -dir $bsp_dir
hsi::close_hw_design [hsi::current_hw_design]
puts "BSP generated at: $bsp_dir"

# ---- Step 2: Build BSP (compile drivers + libxil.a) ----
puts "\n--- Step 2: Build BSP libraries ---"
set build_result [exec make -C $bsp_dir 2>@1]
puts $build_result

set libxil "$bsp_dir/$proc_inst/lib/libxil.a"
if {![file exists $libxil]} {
    puts "ERROR: BSP build failed — libxil.a not found"
    exit 1
}
puts "BSP library: $libxil ([file size $libxil] bytes)"

# ---- Step 3: Compile application ----
puts "\n--- Step 3: Compile application ---"
set bsp_inc "$bsp_dir/$proc_inst/include"
set cc "/scratch/AMDDesignTools/2025.2/Vitis/gnu/aarch64/lin/aarch64-none/bin/aarch64-none-elf-gcc"

# Only compile main.c and any files that are not BSP-generated init files
set all_c_files [glob -nocomplain "$app_src_dir/*.c"]
set c_files {}
foreach f $all_c_files {
    set base [file tail $f]
    if {$base eq "psu_init.c" || $base eq "psu_init_gpl.c"} { continue }
    lappend c_files $f
}
if {[llength $c_files] == 0} {
    puts "ERROR: No .c files in $app_src_dir (excluding psu_init files)"
    exit 1
}
puts "Source files: $c_files"

set obj_files {}
foreach src $c_files {
    set base [file rootname [file tail $src]]
    set obj "$app_dir/${base}.o"
    set cmd "$cc -Wall -Wextra -O2 -march=armv8-a -ffreestanding -I$bsp_inc -I$app_src_dir -c $src -o $obj"
    puts "  Compiling: [file tail $src]"
    set compile_out [exec {*}$cmd 2>@1]
    if {$compile_out ne ""} { puts "    $compile_out" }
    lappend obj_files $obj
}
puts "Compiled [llength $obj_files] object files."

# ---- Step 4: Link into .elf ----
puts "\n--- Step 4: Link application ---"

set repo_root [file dirname [file dirname [file normalize [info script]]]]
set ld_script "$repo_root/scripts/lscript_a53.ld"
if {![file exists $ld_script]} {
    puts "WARNING: Linker script not found at $ld_script — skipping link step."
    puts "  Compile-only test PASSED."
} else {
    set elf_path "$build_dir/${app_name}.elf"
    set bsp_lib "$bsp_dir/$proc_inst/lib"

    set link_cmd [list $cc -march=armv8-a -ffreestanding -nostdlib \
        -L$bsp_lib -T $ld_script \
        {*}$obj_files \
        -Wl,--start-group,-lxil,-lgcc,-lc,--end-group \
        -o $elf_path]
    puts "  Linking: $elf_path"
    set link_out [exec {*}$link_cmd 2>@1]
    if {$link_out ne ""} { puts "    $link_out" }

    if {[file exists $elf_path]} {
        puts "\nLink SUCCEEDED: $elf_path ([file size $elf_path] bytes)"
        set elf_info [exec file $elf_path]
        puts "  $elf_info"
    } else {
        puts "\nERROR: Link failed — ELF not produced."
        exit 1
    }
}

puts "\n============================================"
puts "Build Summary"
puts "  BSP:     $libxil"
puts "  Objects: [llength $obj_files] files"
if {[info exists elf_path] && [file exists $elf_path]} {
    puts "  ELF:     $elf_path"
}
puts "============================================"
puts "\nDone."
exit 0
