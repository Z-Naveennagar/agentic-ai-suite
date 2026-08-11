# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def packet_boundaries_survive_backpressure(dut):
    rng = random.Random(0xA815)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.m_axis_tready.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0

    words = [rng.getrandbits(32) for _ in range(205)]
    expected = [(word, int(index % 8 == 7)) for index, word in enumerate(words)]
    sent = 0
    received = []
    held = None
    driving = False

    for _ in range(5000):
        await FallingEdge(dut.clk)
        ready = rng.randrange(4) != 0
        dut.m_axis_tready.value = ready
        if sent < len(words):
            if not driving:
                driving = rng.randrange(5) != 0
            dut.s_axis_tvalid.value = driving
            dut.s_axis_tdata.value = words[sent]
        else:
            dut.s_axis_tvalid.value = 0
        await Timer(1, unit="ns")

        current = (int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value))
        if int(dut.m_axis_tvalid.value) and not ready:
            if held is not None:
                assert current == held
            held = current
        else:
            held = None
        input_fire = int(dut.s_axis_tvalid.value) and int(dut.s_axis_tready.value)
        output_fire = int(dut.m_axis_tvalid.value) and ready
        await RisingEdge(dut.clk)
        if input_fire:
            sent += 1
            driving = False
        if output_fire:
            received.append(current)
        if len(received) == len(expected):
            break

    assert received == expected
