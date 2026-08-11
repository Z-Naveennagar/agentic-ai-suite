# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def signed(value):
    return value - 65536 if value & 0x8000 else value


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def fixed_point_dc_block_model_and_state_control(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.m_ready.value = 1
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1

    rng = random.Random(0xDCB)
    samples = [10000] * 40 + [-12000] * 12
    samples += [rng.randrange(-20000, 20001) for _ in range(100)]
    x_previous = 0
    y_previous = 0
    dut.s_valid.value = 1
    for index, sample in enumerate(samples):
        if index % 13 == 5:
            dut.s_valid.value = 0
            await tick(dut)
            assert int(dut.m_valid.value) == 0
            dut.s_valid.value = 1
        next_y = sample - x_previous + ((y_previous * 15) >> 4)
        expected = max(-32768, min(32767, next_y))
        x_previous, y_previous = sample, next_y
        dut.s_data.value = sample & 0xFFFF
        await tick(dut)
        assert int(dut.m_valid.value) == 1
        assert signed(int(dut.m_data.value)) == expected

    dut.m_ready.value = 0
    held = int(dut.m_data.value)
    await tick(dut)
    await tick(dut)
    assert int(dut.s_ready.value) == 0
    assert int(dut.m_data.value) == held

    dut.rst_n.value = 0
    await tick(dut)
    dut.rst_n.value = 1
    dut.m_ready.value = 1
    dut.s_data.value = 1000
    await tick(dut)
    assert signed(int(dut.m_data.value)) == 1000
