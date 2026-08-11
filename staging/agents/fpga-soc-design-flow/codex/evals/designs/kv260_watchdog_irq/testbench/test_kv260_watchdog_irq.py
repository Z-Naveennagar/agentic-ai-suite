# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut, cycles=1):
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")


async def reload(dut, timeout):
    dut.timeout_cycles.value = timeout
    dut.reload.value = 1
    await tick(dut)
    dut.reload.value = 0


@cocotb.test()
async def watchdog_expiry_sticky_and_rearm(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.resetn.value = 0
    dut.enable.value = 0
    dut.reload.value = 0
    dut.clear_expired.value = 0
    dut.timeout_cycles.value = 0
    await tick(dut, 2)
    dut.resetn.value = 1

    await reload(dut, 3)
    await tick(dut, 4)
    assert int(dut.irq_o.value) == 0
    dut.enable.value = 1
    await tick(dut, 2)
    assert int(dut.irq_o.value) == 0
    await tick(dut)
    assert int(dut.irq_o.value) == 1
    assert int(dut.expired_sticky_o.value) == 1
    await tick(dut, 3)
    assert int(dut.irq_o.value) == 0

    dut.clear_expired.value = 1
    await tick(dut)
    dut.clear_expired.value = 0
    assert int(dut.expired_sticky_o.value) == 0
    await reload(dut, 2)
    await tick(dut, 2)
    assert int(dut.irq_o.value) == 1
