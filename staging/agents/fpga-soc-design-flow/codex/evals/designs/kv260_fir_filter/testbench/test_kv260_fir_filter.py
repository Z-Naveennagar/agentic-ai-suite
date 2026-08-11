# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


@cocotb.test()
async def exact_fir_convolution(dut):
    rng = random.Random(0xF18)
    coefficients = [1, 2, 3, 4, 4, 3, 2, 1]
    history = [0] * 7
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.s_valid.value = 0
    dut.s_data.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0

    samples = [32767, -32768, 0, 1, -1] + [
        rng.randrange(-32768, 32768) for _ in range(250)
    ]
    expected_outputs = []

    for sample in samples:
        for _ in range(rng.randrange(3)):
            await FallingEdge(dut.clk)
            dut.s_valid.value = 0
            await RisingEdge(dut.clk)
            await Timer(1, unit="ns")
            assert int(dut.m_valid.value) == 0

        expected = sample * coefficients[0]
        expected += sum(x * c for x, c in zip(history, coefficients[1:]))
        expected_outputs.append(expected)
        history = [sample] + history[:-1]

        await FallingEdge(dut.clk)
        dut.s_data.value = sample & 0xFFFF
        dut.s_valid.value = 1
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.m_valid.value) == 1
        assert signed(int(dut.m_data.value), 36) == expected_outputs[-1]

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.m_valid.value) == 0
