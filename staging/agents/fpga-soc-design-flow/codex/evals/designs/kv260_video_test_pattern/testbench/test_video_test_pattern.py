# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


COLORS = [0xFFFFFF, 0xFFFF00, 0x00FFFF, 0x00FF00, 0xFF00FF, 0xFF0000, 0x0000FF, 0x000000]


@cocotb.test()
async def frames_hold_under_stalls(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst_n.value = 0
    dut.enable.value = 0
    dut.frame_width.value = 16
    dut.frame_height.value = 3
    dut.m_axis_tready.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    dut.enable.value = 1

    expected = []
    for _frame in range(2):
        for y in range(3):
            for x in range(16):
                expected.append((COLORS[(x * 8) // 16], int(x == 0 and y == 0), int(x == 15)))

    rng = random.Random(1602)
    got = []
    held = None
    for _ in range(2000):
        await FallingEdge(dut.clk)
        dut.m_axis_tready.value = rng.randrange(5) != 0
        await Timer(1, units="ns")
        if dut.m_axis_tvalid.value:
            now = (int(dut.m_axis_tdata.value), int(dut.m_axis_tuser.value), int(dut.m_axis_tlast.value))
            if dut.m_axis_tready.value:
                got.append(now)
                held = None
            else:
                if held is not None:
                    assert now == held
                held = now
        await RisingEdge(dut.clk)
        if len(got) == len(expected):
            break

    assert got == expected
