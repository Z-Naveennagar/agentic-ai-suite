# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def sample(dut, cycles):
    values = []
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        values.append(int(dut.pwm_o.value))
    return values


@cocotb.test()
async def pwm_ratios_and_corner_cases(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.resetn.value = 0
    dut.period_i.value = 8
    dut.duty_i.value = 3
    await sample(dut, 2)
    dut.resetn.value = 1
    normal = await sample(dut, 16)
    assert sum(normal) == 6

    dut.duty_i.value = 0
    # Runtime values are allowed to take effect at the next period boundary.
    # Discard one complete old period before checking the new steady state.
    await sample(dut, 8)
    assert not any(await sample(dut, 8))
    dut.duty_i.value = 8
    await sample(dut, 8)
    assert all(await sample(dut, 8))
    dut.period_i.value = 0
    await sample(dut, 8)
    assert not any(await sample(dut, 4))
