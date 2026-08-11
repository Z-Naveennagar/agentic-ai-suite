# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def pack_window(pixels):
    return sum((value & 0xFF) << (8 * index) for index, value in enumerate(pixels))


def sobel(pixels, border):
    if border:
        return 0
    p0, p1, p2, p3, _, p5, p6, p7, p8 = pixels
    gx = -p0 + p2 - 2 * p3 + 2 * p5 - p6 + p8
    gy = p0 + 2 * p1 + p2 - p6 - 2 * p7 - p8
    return min(255, abs(gx) + abs(gy))


@cocotb.test()
async def sobel_windows_and_line_control(dut):
    rng = random.Random(0x50BE1)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    dut.s_valid.value = 0
    dut.s_window.value = 0
    dut.s_line_start.value = 0
    dut.s_line_end.value = 0
    dut.s_border.value = 0
    dut.m_ready.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0

    directed = [
        ([0] * 9, 0),
        ([100] * 9, 0),
        ([0, 0, 255, 0, 0, 255, 0, 0, 255], 0),
        ([255, 255, 255, 0, 0, 0, 0, 0, 0], 0),
        ([255] * 9, 1),
    ]
    items = []
    for index, (pixels, border) in enumerate(directed):
        items.append((pixels, int(index == 0), int(index == len(directed) - 1), border))
    for index in range(150):
        items.append(
            (
                [rng.randrange(256) for _ in range(9)],
                int(index % 17 == 0),
                int(index % 17 == 16),
                int(rng.randrange(11) == 0),
            )
        )
    expected = [(sobel(p, b), ls, le, b) for p, ls, le, b in items]
    sent = 0
    received = []
    held = None
    driving = False

    for _ in range(5000):
        await FallingEdge(dut.clk)
        ready = rng.randrange(4) != 0
        dut.m_ready.value = ready
        if sent < len(items):
            pixels, line_start, line_end, border = items[sent]
            if not driving:
                driving = rng.randrange(5) != 0
            dut.s_valid.value = driving
            dut.s_window.value = pack_window(pixels)
            dut.s_line_start.value = line_start
            dut.s_line_end.value = line_end
            dut.s_border.value = border
        else:
            dut.s_valid.value = 0
        await Timer(1, unit="ns")
        current = (
            int(dut.m_magnitude.value),
            int(dut.m_line_start.value),
            int(dut.m_line_end.value),
            int(dut.m_border.value),
        )
        if int(dut.m_valid.value) and not ready:
            if held is not None:
                assert current == held
            held = current
        else:
            held = None
        input_fire = int(dut.s_valid.value) and int(dut.s_ready.value)
        output_fire = int(dut.m_valid.value) and ready
        await RisingEdge(dut.clk)
        if input_fire:
            sent += 1
            driving = False
        if output_fire:
            received.append(current)
        if len(received) == len(expected):
            break

    assert received == expected
