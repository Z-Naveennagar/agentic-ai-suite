# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def signed(value, bits=16):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def model(sample, gain):
    value = (sample * gain) >> 14
    return max(-32768, min(32767, value))


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def gain_scaling_saturation_and_backpressure(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.gain_q14.value = 0
    dut.m_ready.value = 1
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1

    rng = random.Random(0xA6A1)
    vectors = [(0, 0), (12345, 0x4000), (-12345, 0x2000),
               (30000, 0x8000), (-30000, 0x8000)]
    vectors += [(rng.randrange(-32768, 32768), rng.randrange(0, 65536))
                for _ in range(100)]
    for sample, gain in vectors:
        dut.s_data.value = sample & 0xFFFF
        dut.gain_q14.value = gain
        dut.s_valid.value = 1
        await tick(dut)
        assert int(dut.m_valid.value) == 1
        assert signed(int(dut.m_data.value)) == model(sample, gain)

    dut.m_ready.value = 0
    held = int(dut.m_data.value)
    dut.s_data.value = 1
    dut.gain_q14.value = 0x4000
    await tick(dut)
    await tick(dut)
    assert int(dut.s_ready.value) == 0
    assert int(dut.m_data.value) == held
    dut.s_valid.value = 0
    dut.rst_n.value = 0
    await tick(dut)
    assert int(dut.m_valid.value) == 0
