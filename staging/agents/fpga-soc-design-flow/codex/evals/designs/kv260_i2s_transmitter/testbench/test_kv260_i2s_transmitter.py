# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def serializes_stereo_i2s_frame(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.enable.value = 0
    dut.sample_valid.value = 0
    dut.left_sample.value = 0
    dut.right_sample.value = 0
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1
    dut.enable.value = 1
    await tick(dut)
    assert int(dut.sample_ready.value) == 1

    left = 0xA5C3
    right = 0x3C5A
    dut.left_sample.value = left
    dut.right_sample.value = right
    dut.sample_valid.value = 1
    await tick(dut)
    dut.sample_valid.value = 0
    assert int(dut.busy.value) == 1
    assert int(dut.sample_ready.value) == 0

    observed = []
    previous_bclk = int(dut.i2s_bclk.value)
    for _ in range(400):
        await tick(dut)
        current_bclk = int(dut.i2s_bclk.value)
        if previous_bclk == 1 and current_bclk == 0:
            observed.append((int(dut.i2s_lrclk.value), int(dut.i2s_sdata.value)))
        previous_bclk = current_bclk
        if len(observed) == 34:
            break

    left_bits = [(left >> bit) & 1 for bit in range(15, -1, -1)]
    right_bits = [(right >> bit) & 1 for bit in range(15, -1, -1)]
    expected = [(0, 0)] + [(0, bit) for bit in left_bits]
    expected += [(1, 0)] + [(1, bit) for bit in right_bits]
    assert observed == expected

    for _ in range(20):
        await tick(dut)
        if int(dut.busy.value) == 0:
            break
    assert int(dut.sample_ready.value) == 1

    dut.enable.value = 0
    await tick(dut)
    assert int(dut.i2s_bclk.value) == 0
    assert int(dut.i2s_lrclk.value) == 0
    assert int(dut.i2s_sdata.value) == 0
