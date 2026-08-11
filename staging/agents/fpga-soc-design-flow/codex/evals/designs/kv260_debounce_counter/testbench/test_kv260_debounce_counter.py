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
async def glitches_are_rejected_and_edges_counted(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.resetn.value = 0
    dut.signal_i.value = 0
    await tick(dut, 3)
    dut.resetn.value = 1

    dut.signal_i.value = 1
    await tick(dut, 2)
    dut.signal_i.value = 0
    await tick(dut, 6)
    assert int(dut.debounced_o.value) == 0
    assert int(dut.edge_count_o.value) == 0

    dut.signal_i.value = 1
    await tick(dut, 6)
    assert int(dut.debounced_o.value) == 1
    assert int(dut.rise_pulse_o.value) == 1
    assert int(dut.edge_count_o.value) == 1
    await tick(dut)
    assert int(dut.rise_pulse_o.value) == 0

    dut.signal_i.value = 0
    await tick(dut, 6)
    assert int(dut.debounced_o.value) == 0
    assert int(dut.edge_count_o.value) == 1
    dut.signal_i.value = 1
    await tick(dut, 6)
    assert int(dut.edge_count_o.value) == 2
