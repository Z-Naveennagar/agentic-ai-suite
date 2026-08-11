# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def snapshot_windows_are_exact_and_stable(dut):
    rng = random.Random(0x44)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.m_ready.value = 0
    for signal in ("s_read_beat", "s_write_beat", "s_stall", "s_snapshot"):
        getattr(dut, signal).value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    windows = [
        [(0, 0, 0)],
        [(1, 0, 0), (0, 1, 1), (1, 1, 0)],
        [(rng.randrange(2), rng.randrange(2), rng.randrange(2)) for _ in range(31)],
        [(1, 1, 1)],
    ]
    items = []
    expected = []
    for window in windows:
        for index, (read, write, stall) in enumerate(window):
            items.append((read, write, stall, int(index == len(window) - 1)))
        expected.append(
            (
                len(window),
                sum(event[0] for event in window),
                sum(event[1] for event in window),
                sum(event[2] for event in window),
            )
        )

    sent = 0
    received = []
    held = None
    for _ in range(2500):
        await FallingEdge(dut.clk)
        ready = rng.randrange(3) != 0
        dut.m_ready.value = ready
        if sent < len(items):
            read, write, stall, snapshot = items[sent]
            dut.s_valid.value = 1
            dut.s_read_beat.value = read
            dut.s_write_beat.value = write
            dut.s_stall.value = stall
            dut.s_snapshot.value = snapshot
        else:
            dut.s_valid.value = 0
        await Timer(1, unit="ns")
        now = (
            int(dut.m_cycles.value),
            int(dut.m_read_beats.value),
            int(dut.m_write_beats.value),
            int(dut.m_stalls.value),
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
