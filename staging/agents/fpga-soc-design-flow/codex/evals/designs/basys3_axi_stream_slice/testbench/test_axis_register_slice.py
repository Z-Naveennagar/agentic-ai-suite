# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def preserves_stream_under_backpressure(dut):
    rng = random.Random(0xA51C)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    dut.m_axis_tready.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.rst.value = 0

    transfers = [(rng.getrandbits(32), int(index % 11 == 10)) for index in range(200)]
    sent = 0
    received = []
    stalled_value = None

    for _ in range(2000):
        await FallingEdge(dut.clk)
        ready = rng.randrange(4) != 0
        dut.m_axis_tready.value = ready

        if sent < len(transfers):
            data, last = transfers[sent]
            dut.s_axis_tvalid.value = 1
            dut.s_axis_tdata.value = data
            dut.s_axis_tlast.value = last
        else:
            dut.s_axis_tvalid.value = 0

        await Timer(1, unit="ns")
        if int(dut.m_axis_tvalid.value) and not ready:
            current = (int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value))
            if stalled_value is not None:
                assert current == stalled_value, "output changed while backpressured"
            stalled_value = current
        else:
            stalled_value = None

        input_fire = int(dut.s_axis_tvalid.value) and int(dut.s_axis_tready.value)
        output_fire = int(dut.m_axis_tvalid.value) and ready
        output_value = (int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value))
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if input_fire:
            sent += 1
        if output_fire:
            received.append(output_value)

        if len(received) == len(transfers):
            break

    assert sent == len(transfers)
    assert received == transfers

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.m_axis_tvalid.value) == 0
