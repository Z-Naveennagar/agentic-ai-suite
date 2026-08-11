# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def gray(rgb):
    return (77 * ((rgb >> 16) & 255) + 150 * ((rgb >> 8) & 255) + 29 * (rgb & 255) + 128) >> 8


def model(image, threshold):
    g = [[gray(pixel) for pixel in row] for row in image]
    result = []
    for y in range(2, len(g)):
        edge_d1 = edge_d2 = 0
        for x in range(2, len(g[0])):
            gx = g[y - 2][x] + 2 * g[y - 1][x] + g[y][x] - g[y - 2][x - 2] - 2 * g[y - 1][x - 2] - g[y][x - 2]
            gy = g[y][x - 2] + 2 * g[y][x - 1] + g[y][x] - g[y - 2][x - 2] - 2 * g[y - 2][x - 1] - g[y - 2][x]
            edge = int(abs(gx) + abs(gy) >= threshold)
            dilated = edge | edge_d1 | edge_d2
            result.append((0xFF if dilated else 0, int(y == 2 and x == 2), int(x == len(g[0]) - 1)))
            edge_d2, edge_d1 = edge_d1, edge
    return result


@cocotb.test()
async def exact_sobel_threshold_dilation_with_stalls(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst_n.value = 0
    dut.s_axis_tvalid.value = 0
    dut.m_axis_tready.value = 0
    width, height, threshold = 8, 6, 180
    dut.input_width.value = width
    dut.threshold.value = threshold
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    image = []
    for y in range(height):
        row = []
        for x in range(width):
            value = 20 if x < 4 else 220
            if y == 4 and x in (1, 2):
                value = 180
            row.append((value << 16) | (value << 8) | value)
        image.append(row)
    stream = [
        (image[y][x], int(x == 0 and y == 0), int(x == width - 1))
        for y in range(height) for x in range(width)
    ]
    expected = model(image, threshold)

    rng = random.Random(2007)
    sent = 0
    got = []
    held = None
    for _ in range(5000):
        await FallingEdge(dut.clk)
        dut.m_axis_tready.value = rng.randrange(5) != 0
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
