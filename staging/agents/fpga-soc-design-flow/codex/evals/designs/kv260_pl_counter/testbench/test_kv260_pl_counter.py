# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut, cycles=1):
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")


@cocotb.test()
async def counter_control_and_terminal_pulse(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.resetn.value = 0
    dut.enable.value = 0
    dut.clear.value = 0
    await tick(dut, 2)
    dut.resetn.value = 1
    await tick(dut)
    assert int(dut.count.value) == 0

    dut.enable.value = 1
    await tick(dut, 5)
    assert int(dut.count.value) == 5
    dut.enable.value = 0
    await tick(dut, 3)
    assert int(dut.count.value) == 5

    dut.clear.value = 1
    dut.enable.value = 1
    await tick(dut)
    assert int(dut.count.value) == 0
    assert int(dut.terminal_pulse.value) == 0
    dut.clear.value = 0
    await tick(dut, 15)
    assert int(dut.count.value) == 15
    await tick(dut)
    assert int(dut.count.value) == 0
    assert int(dut.terminal_pulse.value) == 1
    await tick(dut)
    assert int(dut.terminal_pulse.value) == 0
