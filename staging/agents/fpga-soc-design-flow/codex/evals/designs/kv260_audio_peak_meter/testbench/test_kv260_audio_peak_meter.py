# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def reports_windowed_absolute_peak(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.peak_ready.value = 1
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1

    windows = [
        ([0, 1, -1, 17, -22, 4, 9, -3], 22),
        ([32767, -32768, 10, -20, 0, 6, 7, 8], 32768),
    ]
    for samples, expected in windows:
        for index, sample in enumerate(samples):
            if index == 4:
                dut.s_valid.value = 0
                await tick(dut)
                assert int(dut.peak_valid.value) == 0
            dut.s_data.value = sample & 0xFFFF
            dut.s_valid.value = 1
            await tick(dut)
        assert int(dut.peak_valid.value) == 1
        assert int(dut.peak_value.value) == expected

    dut.peak_ready.value = 0
    held = int(dut.peak_value.value)
    for _ in range(4):
        await tick(dut)
        assert int(dut.s_ready.value) == 0
        assert int(dut.peak_value.value) == held

    dut.rst_n.value = 0
    await tick(dut)
    assert int(dut.peak_valid.value) == 0
