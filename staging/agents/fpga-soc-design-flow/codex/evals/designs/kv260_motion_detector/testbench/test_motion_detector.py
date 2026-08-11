# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def paired_pixel_motion_with_backpressure(dut):
    rng = random.Random(0x41)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.m_ready.value = 0
    for signal in ("s_current", "s_reference", "s_threshold", "s_user", "s_last"):
        getattr(dut, signal).value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    items = [
        (0, 0, 0, 1, 0),
        (100, 90, 10, 0, 0),
        (90, 100, 11, 0, 0),
        (255, 0, 200, 0, 1),
    ]
    for index in range(96):
        items.append(
            (
                rng.randrange(256),
                rng.randrange(256),
                rng.randrange(256),
                int(index == 0),
                int(index == 95),
            )
        )
    expected = []
    for current, reference, threshold, user, last in items:
        diff = abs(current - reference)
        expected.append((diff, int(diff >= threshold), user, last))

    sent = 0
    received = []
    held = None
    for _ in range(3000):
        await FallingEdge(dut.clk)
        ready = rng.randrange(4) != 0
        dut.m_ready.value = ready
        if sent < len(items):
            current, reference, threshold, user, last = items[sent]
            dut.s_valid.value = 1
            dut.s_current.value = current
            dut.s_reference.value = reference
            dut.s_threshold.value = threshold
            dut.s_user.value = user
            dut.s_last.value = last
        else:
            dut.s_valid.value = 0
        await Timer(1, unit="ns")
        now = (
            int(dut.m_difference.value),
            int(dut.m_motion.value),
            int(dut.m_user.value),
            int(dut.m_last.value),
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
    assert sent == len(items)
    assert received == expected
