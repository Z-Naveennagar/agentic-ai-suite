# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def routes_all_channel_modes_and_holds_on_stall(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.route_select.value = 0
    dut.left_in.value = 0
    dut.right_in.value = 0
    dut.m_ready.value = 1
    await tick(dut)
    await tick(dut)
    dut.rst_n.value = 1

    left, right = 0x8123, 0x7ACE
    expected = [(left, right), (right, left), (left, left), (right, right)]
    dut.s_valid.value = 1
    for route, pair in enumerate(expected):
        dut.route_select.value = route
        dut.left_in.value = left
        dut.right_in.value = right
        await tick(dut)
        assert int(dut.m_valid.value) == 1
        assert (int(dut.left_out.value), int(dut.right_out.value)) == pair

    dut.m_ready.value = 0
    held = (int(dut.left_out.value), int(dut.right_out.value))
    dut.route_select.value = 0
    dut.left_in.value = 1
    dut.right_in.value = 2
    for _ in range(4):
        await tick(dut)
        assert int(dut.s_ready.value) == 0
        assert (int(dut.left_out.value), int(dut.right_out.value)) == held

    dut.rst_n.value = 0
    await tick(dut)
    assert int(dut.m_valid.value) == 0
