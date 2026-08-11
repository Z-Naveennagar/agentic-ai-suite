# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut):
    await RisingEdge(dut.aclk)
    await Timer(1, unit="ns")


@cocotb.test()
async def elastic_throughput_and_backpressure(dut):
    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    dut.aresetn.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    dut.s_axis_tvalid.value = 0
    dut.m_axis_tready.value = 0
    await tick(dut)
    await tick(dut)
    dut.aresetn.value = 1

    dut.s_axis_tdata.value = 0x12345678
    dut.s_axis_tlast.value = 1
    dut.s_axis_tvalid.value = 1
    await tick(dut)
    dut.s_axis_tvalid.value = 0
    assert int(dut.m_axis_tvalid.value) == 1
    assert int(dut.m_axis_tdata.value) == 0x12345678
    assert int(dut.m_axis_tlast.value) == 1
    for _ in range(3):
        await tick(dut)
        assert int(dut.m_axis_tdata.value) == 0x12345678
        assert int(dut.m_axis_tlast.value) == 1

    dut.m_axis_tready.value = 1
    dut.s_axis_tvalid.value = 1
    dut.s_axis_tdata.value = 0xABC00000
    dut.s_axis_tlast.value = 0
    await tick(dut)
    for index in range(1, 5):
        assert int(dut.m_axis_tdata.value) == 0xABC00000 + index - 1
        dut.s_axis_tdata.value = 0xABC00000 + index
        dut.s_axis_tlast.value = int(index == 4)
        await tick(dut)
    assert int(dut.m_axis_tdata.value) == 0xABC00004
    assert int(dut.m_axis_tlast.value) == 1
