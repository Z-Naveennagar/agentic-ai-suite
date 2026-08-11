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
async def ramps_mute_and_unmute_per_accepted_sample(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.mute.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 8000
    dut.m_ready.value = 1
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1
    assert int(dut.gain_step.value) == 8

    dut.mute.value = 1
    dut.s_valid.value = 1
    outputs = []
    for gain in range(7, -1, -1):
        await tick(dut)
        outputs.append(signed(int(dut.m_data.value)))
        assert int(dut.gain_step.value) == gain
    assert outputs == [8000 * gain >> 3 for gain in range(7, -1, -1)]

    dut.s_valid.value = 0
    for _ in range(3):
        await tick(dut)
        assert int(dut.gain_step.value) == 0

    dut.mute.value = 0
    dut.s_valid.value = 1
    outputs = []
    for gain in range(1, 9):
        await tick(dut)
        outputs.append(signed(int(dut.m_data.value)))
        assert int(dut.gain_step.value) == gain
    assert outputs == [8000 * gain >> 3 for gain in range(1, 9)]

    dut.m_ready.value = 0
    held = (int(dut.m_data.value), int(dut.gain_step.value))
    await tick(dut)
    await tick(dut)
    assert (int(dut.m_data.value), int(dut.gain_step.value)) == held
