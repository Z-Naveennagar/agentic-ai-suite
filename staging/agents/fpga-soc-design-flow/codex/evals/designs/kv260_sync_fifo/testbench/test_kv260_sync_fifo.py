# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def fifo_order_boundaries_wrap_and_simultaneous_io(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.resetn.value = 0
    dut.wr_en.value = 0
    dut.wr_data.value = 0
    dut.rd_en.value = 0
    await tick(dut)
    await tick(dut)
    dut.resetn.value = 1
    await tick(dut)
    assert int(dut.empty.value) == 1
    assert int(dut.level.value) == 0

    dut.wr_en.value = 1
    for value in range(16):
        dut.wr_data.value = 0x1000 + value
        await tick(dut)
    assert int(dut.full.value) == 1
    assert int(dut.level.value) == 16
    dut.wr_data.value = 0xDEADBEEF
    await tick(dut)
    assert int(dut.level.value) == 16

    dut.wr_en.value = 0
    dut.rd_en.value = 1
    for value in range(8):
        await tick(dut)
        assert int(dut.rd_data.value) == 0x1000 + value
    assert int(dut.level.value) == 8

    dut.wr_en.value = 1
    for value in range(8):
        dut.wr_data.value = 0x2000 + value
        await tick(dut)
        assert int(dut.rd_data.value) == 0x1008 + value
        assert int(dut.level.value) == 8

    dut.wr_en.value = 0
    for value in range(8):
        await tick(dut)
        assert int(dut.rd_data.value) == 0x2000 + value
    assert int(dut.empty.value) == 1
    dut.rd_en.value = 1
    await tick(dut)
    assert int(dut.level.value) == 0
