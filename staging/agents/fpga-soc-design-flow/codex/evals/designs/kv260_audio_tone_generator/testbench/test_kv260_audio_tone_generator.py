# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def signed(value):
    return value - 65536 if value & 0x8000 else value


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def deterministic_square_wave_and_stall(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.enable.value = 0
    dut.phase_increment.value = 0x40000000
    dut.amplitude.value = 12000
    dut.m_ready.value = 1
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1
    dut.enable.value = 1

    observed = []
    for _ in range(8):
        await tick(dut)
        assert int(dut.m_valid.value) == 1
        observed.append(signed(int(dut.m_data.value)))
    assert observed == [12000, 12000, -12000, -12000] * 2

    dut.m_ready.value = 0
    held = int(dut.m_data.value)
    for _ in range(4):
        await tick(dut)
        assert int(dut.m_data.value) == held

    dut.enable.value = 0
    await tick(dut)
    assert int(dut.m_valid.value) == 0
    dut.enable.value = 1
    dut.m_ready.value = 1
    await tick(dut)
    assert signed(int(dut.m_data.value)) == 12000
