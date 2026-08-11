# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def clamp_average_sidebands_and_stalls(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst_n.value = 0
    dut.s_axis_tvalid.value = 0
    dut.m_axis_tready.value = 0
    dut.input_width.value = 6
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    image = [
        [0, 16, 17, 20, 100, 255],
        [15, 18, 30, 40, 80, 120],
        [16, 17, 18, 19, 20, 21],
        [200, 180, 160, 140, 120, 100],
    ]
    stream = []
    for y, row in enumerate(image):
        for x, value in enumerate(row):
            stream.append((value, int(x == 0 and y == 0), int(x == 5)))

    def clamp(value):
        return max(value - 16, 0)

    expected = []
    for y in range(1, len(image), 2):
        for x in range(1, 6, 2):
            avg = sum(clamp(image[yy][xx]) for yy in (y - 1, y) for xx in (x - 1, x)) // 4
            expected.append((avg, int(y == 1 and x == 1), int(x == 5)))

    rng = random.Random(1906)
    sent = 0
    got = []
    held = None
    for _ in range(3000):
        await FallingEdge(dut.clk)
        dut.m_axis_tready.value = rng.randrange(4) != 0
        if sent < len(stream):
            data, user, last = stream[sent]
            dut.s_axis_tvalid.value = 1
            dut.s_axis_tdata.value = data
            dut.s_axis_tuser.value = user
            dut.s_axis_tlast.value = last
        else:
            dut.s_axis_tvalid.value = 0
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
        if dut.s_axis_tvalid.value and dut.s_axis_tready.value:
            sent += 1
        await RisingEdge(dut.clk)
        if len(got) == len(expected):
            break

    assert got == expected
