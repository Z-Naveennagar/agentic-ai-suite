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
async def mixes_signed_stereo_with_elastic_output(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.left_data.value = 0
    dut.right_data.value = 0
    dut.m_ready.value = 1
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1

    rng = random.Random(0x524)
    vectors = [(32767, 32767), (-32768, -32768), (32767, -32768),
               (1, 0), (-1, 0)]
    vectors += [(rng.randrange(-32768, 32768), rng.randrange(-32768, 32768))
                for _ in range(128)]
    for left, right in vectors:
        dut.left_data.value = left & 0xFFFF
        dut.right_data.value = right & 0xFFFF
        dut.s_valid.value = 1
        await tick(dut)
        assert int(dut.m_valid.value) == 1
        assert signed(int(dut.mono_data.value)) == ((left + right) >> 1)

    dut.m_ready.value = 0
    held = int(dut.mono_data.value)
    await tick(dut)
    await tick(dut)
    assert int(dut.s_ready.value) == 0
    assert int(dut.mono_data.value) == held
