# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def cycle(dut, event=0, clear=0):
    dut.event_i.value = event
    dut.clear_i.value = clear
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def pulse_event(dut):
    await cycle(dut, event=1)
    await cycle(dut, event=0)


@cocotb.test()
async def reset_clear_edges_and_overflow(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    dut.event_i.value = 0
    dut.clear_i.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.rst.value = 0

    await pulse_event(dut)
    assert int(dut.count_o.value) == 1

    await cycle(dut, event=1)
    await cycle(dut, event=1)
    await cycle(dut, event=1)
    assert int(dut.count_o.value) == 2, "held-high input must count only one rising edge"
    await cycle(dut, event=0)

    await cycle(dut, event=1, clear=1)
    assert int(dut.count_o.value) == 0, "clear must have priority over event"
    await cycle(dut, event=0)

    for _ in range(255):
        await pulse_event(dut)
    assert int(dut.count_o.value) == 255
    await cycle(dut, event=1)
    assert int(dut.count_o.value) == 0
    assert int(dut.overflow_o.value) == 1
    await cycle(dut, event=0)
    assert int(dut.overflow_o.value) == 0, "overflow must be a one-cycle pulse"

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.count_o.value) == 0
    assert int(dut.overflow_o.value) == 0
