/*
 * Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
 * SPDX-License-Identifier: MIT
 */
/*
 * Linker script for Zynq UltraScale+ Cortex-A53 bare-metal applications.
 * Compatible with standalone BSP boot.S and xil-crt0.S.
 */

_STACK_SIZE = DEFINED(_STACK_SIZE) ? _STACK_SIZE : 0x20000;
_HEAP_SIZE  = DEFINED(_HEAP_SIZE)  ? _HEAP_SIZE  : 0x20000;

MEMORY
{
    psu_ddr_0 : ORIGIN = 0x00000000, LENGTH = 0x10000000
}

ENTRY(_boot)

SECTIONS
{
    .text : {
        KEEP(*(.vectors))
        *(.boot)
        *(.text)
        *(.text.*)
        *(.init)
        *(.fini)
    } > psu_ddr_0

    _init = .;
    _fini = .;

    .init_array : {
        __init_array_start = .;
        *(.init_array)
        *(.init_array.*)
        __init_array_end = .;
    } > psu_ddr_0

    .fini_array : {
        __fini_array_start = .;
        *(.fini_array)
        *(.fini_array.*)
        __fini_array_end = .;
    } > psu_ddr_0

    .rodata : {
        *(.rodata)
        *(.rodata.*)
    } > psu_ddr_0

    .data : {
        *(.data)
        *(.data.*)
    } > psu_ddr_0

    .note : {
        *(.note)
        *(.note.*)
    } > psu_ddr_0

    .sbss (NOLOAD) : {
        __sbss_start = .;
        *(.sbss)
        *(.sbss.*)
        __sbss_end = .;
    } > psu_ddr_0

    .bss (NOLOAD) : {
        . = ALIGN(64);
        __bss_start = .;
        __bss_start__ = .;
        *(.bss)
        *(.bss.*)
        *(COMMON)
        __bss_end = .;
        __bss_end__ = .;
    } > psu_ddr_0

    .heap (NOLOAD) : {
        . = ALIGN(16);
        _heap = .;
        HeapBase = .;
        _heap_start = .;
        . += _HEAP_SIZE;
        _heap_end = .;
        HeapLimit = .;
    } > psu_ddr_0

    .stack (NOLOAD) : {
        . = ALIGN(16);
        _stack_end = .;
        . += _STACK_SIZE;
        . = ALIGN(16);
        _stack = .;
        __stack = .;
        __el3_stack = .;
    } > psu_ddr_0

    _end = .;

    TTC0BaseAddr = 0xFF110000;
    TTC0TickIntrId = 68;
}
