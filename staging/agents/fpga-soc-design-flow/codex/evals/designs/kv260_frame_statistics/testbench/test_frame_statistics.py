# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def frame_reductions_include_boundary_samples(dut):
    rng = random.Random(0x42)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.m_ready.value = 0
    dut.s_sample.value = 0
    dut.s_frame_first.value = 0
    dut.s_frame_last.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    frames = [
        [37],
        [0, 255, 1, 254],
        [9] * 7,
        list(range(32)),
        [rng.randrange(256) for _ in range(41)],
    ]
    items = []
    expected = []
    for frame in frames:
        for index, sample in enumerate(frame):
            items.append((sample, int(index == 0), int(index == len(frame) - 1)))
        expected.append((min(frame), max(frame), sum(frame) // len(frame), len(frame)))

    sent = 0
    received = []
    held = None
    for _ in range(3000):
        await FallingEdge(dut.clk)
        ready = rng.randrange(3) != 0
        dut.m_ready.value = ready
        if sent < len(items):
            sample, first, last = items[sent]
            dut.s_valid.value = 1
            dut.s_sample.value = sample
            dut.s_frame_first.value = first
            dut.s_frame_last.value = last
        else:
            dut.s_valid.value = 0
        await Timer(1, unit="ns")
        now = (
            int(dut.m_minimum.value),
            int(dut.m_maximum.value),
            int(dut.m_mean.value),
            int(dut.m_count.value),
        )
        if int(dut.m_valid.value) and not ready:
            if held is not None:
                assert now == held
            held = now
        else:
            held = None
        input_fire = int(dut.s_valid.value) and int(dut.s_ready.value)
        output_fire = int(dut.m_valid.value) and ready
        await RisingEdge(dut.clk)
        if input_fire:
            sent += 1
        if output_fire:
            received.append(now)
        if len(received) == len(expected):
            break
    assert received == expected
