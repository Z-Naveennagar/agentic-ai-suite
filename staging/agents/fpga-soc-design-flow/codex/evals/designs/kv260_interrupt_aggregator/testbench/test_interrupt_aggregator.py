# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def cycle(dut, sources=0, mask=0xFF, clear=0):
    dut.sources.value = sources
    dut.mask.value = mask
    dut.clear.value = clear
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


def check(dut, pending, irq, valid, index=0):
    assert int(dut.pending.value) == pending
    assert int(dut.irq.value) == irq
    assert int(dut.priority_valid.value) == valid
    assert int(dut.priority_index.value) == index


@cocotb.test()
async def sticky_masked_priority_and_clear_precedence(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.sources.value = 0
    dut.mask.value = 0
    dut.clear.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    await cycle(dut, sources=0b10100100, mask=0xFF)
    check(dut, 0b10100100, 1, 1, 2)
    await cycle(dut, mask=0b10000000)
    check(dut, 0b10100100, 1, 1, 7)
    await cycle(dut, mask=0)
    check(dut, 0b10100100, 0, 0, 0)
    await cycle(dut, sources=0b00000001, mask=0xFF, clear=0b00100100)
    check(dut, 0b10000001, 1, 1, 0)
    await cycle(dut, sources=0b10000000, mask=0xFF, clear=0b10000000)
    check(dut, 0b00000001, 1, 1, 0)
    await cycle(dut, mask=0xFF, clear=0xFF)
    check(dut, 0, 0, 0, 0)
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    check(dut, 0, 0, 0, 0)
