# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


async def reset(dut):
    dut.rst_n.value = 0
    dut.s_axis_tvalid.value = 0
    dut.m_axis_tready.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1


async def run_frame(dut, width, height, seed):
    pixels = []
    expected = []
    for y in range(height):
        for x in range(width):
            data = (y << 12) | x
            pixels.append((data, int(x == 0 and y == 0), int(x == width - 1)))
            if not (x & 1) and not (y & 1):
                out_last = x == (width - 1 if width & 1 else width - 2)
                expected.append((data, int(x == 0 and y == 0), int(out_last)))

    rng = random.Random(seed)
    sent = 0
    got = []
    held = None
    dut.input_width.value = width
    for _ in range(4000):
        await FallingEdge(dut.clk)
        dut.m_axis_tready.value = rng.randrange(4) != 0
        if sent < len(pixels):
            data, user, last = pixels[sent]
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


@cocotb.test()
async def even_and_odd_width_downscale(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset(dut)
    await run_frame(dut, 8, 6, 1804)
    await reset(dut)
    await run_frame(dut, 7, 5, 1805)
