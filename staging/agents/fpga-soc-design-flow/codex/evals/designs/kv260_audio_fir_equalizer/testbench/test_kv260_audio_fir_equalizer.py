# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def exact_five_tap_response_bubbles_and_stall(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.m_ready.value = 1
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1

    coefficients = [1, 2, 3, 2, 1]
    history = [0] * 4
    rng = random.Random(0xF1E)
    samples = [1, 0, 0, 0, 0, 32767, -32768]
    samples += [rng.randrange(-32768, 32768) for _ in range(100)]
    for index, sample in enumerate(samples):
        if index % 7 == 3:
            dut.s_valid.value = 0
            await tick(dut)
            assert int(dut.m_valid.value) == 0
        expected = sample + sum(x * c for x, c in zip(history, coefficients[1:]))
        history = [sample] + history[:-1]
        dut.s_data.value = sample & 0xFFFF
        dut.s_valid.value = 1
        await tick(dut)
        assert int(dut.m_valid.value) == 1
        assert signed(int(dut.m_data.value), 20) == expected

    dut.m_ready.value = 0
    held = int(dut.m_data.value)
    await tick(dut)
    await tick(dut)
    assert int(dut.s_ready.value) == 0
    assert int(dut.m_data.value) == held

    dut.rst_n.value = 0
    await tick(dut)
    assert int(dut.m_valid.value) == 0
