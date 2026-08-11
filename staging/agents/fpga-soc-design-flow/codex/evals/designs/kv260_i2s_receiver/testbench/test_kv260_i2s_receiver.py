# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def serial_bit(dut, channel, value):
    dut.i2s_lrclk.value = channel
    dut.i2s_sdata.value = value
    dut.i2s_bclk.value = 0
    await tick(dut)
    dut.i2s_bclk.value = 1
    await tick(dut)
    dut.i2s_bclk.value = 0
    await tick(dut)


async def send_word(dut, channel, value):
    await serial_bit(dut, channel, 0)
    for bit in range(15, -1, -1):
        await serial_bit(dut, channel, (value >> bit) & 1)


@cocotb.test()
async def receives_stereo_i2s_frames(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.enable.value = 0
    dut.i2s_bclk.value = 0
    dut.i2s_lrclk.value = 0
    dut.i2s_sdata.value = 0
    dut.sample_ready.value = 0
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1
    dut.enable.value = 1

    left, right = 0x8123, 0x7ACE
    await send_word(dut, 0, left)
    await send_word(dut, 1, right)
    assert int(dut.sample_valid.value) == 1
    assert int(dut.left_sample.value) == left
    assert int(dut.right_sample.value) == right

    held = (int(dut.left_sample.value), int(dut.right_sample.value))
    for _ in range(5):
        await tick(dut)
        assert int(dut.sample_valid.value) == 1
        assert (int(dut.left_sample.value), int(dut.right_sample.value)) == held

    dut.sample_ready.value = 1
    await tick(dut)
    assert int(dut.sample_valid.value) == 0

    dut.rst_n.value = 0
    await tick(dut)
    assert int(dut.sample_valid.value) == 0
    assert int(dut.left_sample.value) == 0
    assert int(dut.right_sample.value) == 0
