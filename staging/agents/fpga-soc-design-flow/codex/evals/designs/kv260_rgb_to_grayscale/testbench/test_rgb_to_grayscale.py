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
    await RisingEdge(dut.clk)


@cocotb.test()
async def bt601_sidebands_and_backpressure(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset(dut)
    rng = random.Random(1501)
    pixels = [
        (0x000000, 1, 0),
        (0xFFFFFF, 0, 0),
        (0xFF0000, 0, 1),
        (0x00FF00, 0, 0),
        (0x0000FF, 0, 1),
    ]
    pixels += [(rng.randrange(1 << 24), 0, i % 11 == 10) for i in range(75)]
    expected = [
        (((77 * ((p >> 16) & 255) + 150 * ((p >> 8) & 255) + 29 * (p & 255) + 128) >> 8), u, l)
        for p, u, l in pixels
    ]

    sent = 0
    received = []
    held = None
    for _ in range(2000):
        await FallingEdge(dut.clk)
        dut.m_axis_tready.value = rng.randrange(4) != 0
        if sent < len(pixels):
            p, u, last = pixels[sent]
            dut.s_axis_tvalid.value = 1
            dut.s_axis_tdata.value = p
            dut.s_axis_tuser.value = u
            dut.s_axis_tlast.value = last
        else:
            dut.s_axis_tvalid.value = 0
        await Timer(1, units="ns")

        if dut.m_axis_tvalid.value:
            now = (int(dut.m_axis_tdata.value), int(dut.m_axis_tuser.value), int(dut.m_axis_tlast.value))
            if not dut.m_axis_tready.value:
                if held is not None:
                    assert now == held
                held = now
            else:
                received.append(now)
                held = None
        if dut.s_axis_tvalid.value and dut.s_axis_tready.value:
            sent += 1
        await RisingEdge(dut.clk)
        if len(received) == len(expected):
            break

    assert received == expected
