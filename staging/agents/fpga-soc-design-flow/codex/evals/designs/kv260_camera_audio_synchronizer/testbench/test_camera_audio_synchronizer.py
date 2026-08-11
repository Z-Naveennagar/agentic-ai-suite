# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def paired_metadata_alignment_and_stalls(dut):
    rng = random.Random(0x49)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.s_valid.value = 0
    dut.m_ready.value = 0
    for name in ("s_camera_epoch", "s_audio_epoch", "s_camera_timestamp",
                 "s_audio_timestamp", "s_tolerance"):
        getattr(dut, name).value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    items = [
        (1, 1, 100, 90, 10),
        (2, 2, 90, 100, 10),
        (3, 3, 100, 89, 10),
        (4, 5, 100, 100, 100),
        (6, 6, (1 << 64) - 2, (1 << 64) - 5, 3),
    ]
    for _ in range(75):
        camera = rng.randrange(1 << 48)
        delta = rng.randrange(-1000, 1001)
        audio = (camera - delta) & ((1 << 64) - 1)
        epoch = rng.randrange(1 << 16)
        same = rng.randrange(4) != 0
        items.append((epoch, epoch if same else (epoch + 1) & 0xFFFF,
                      camera, audio, rng.randrange(1001)))
    expected = []
    for ce, ae, camera, audio, tolerance in items:
        skew = (camera - audio) & ((1 << 65) - 1)
        expected.append((ce, skew, int(ce == ae),
                         int(ce == ae and abs(camera - audio) <= tolerance)))

    sent = 0
    received = []
    held = None
    for _ in range(3000):
        await FallingEdge(dut.clk)
        ready = int(rng.randrange(4) != 0)
        dut.m_ready.value = ready
        if sent < len(items):
            ce, ae, camera, audio, tolerance = items[sent]
            dut.s_valid.value = 1
            dut.s_camera_epoch.value = ce
            dut.s_audio_epoch.value = ae
            dut.s_camera_timestamp.value = camera
            dut.s_audio_timestamp.value = audio
            dut.s_tolerance.value = tolerance
        else:
            dut.s_valid.value = 0
        await Timer(1, unit="ns")
        current = (int(dut.m_epoch.value), int(dut.m_skew.value),
                   int(dut.m_epoch_match.value), int(dut.m_aligned.value))
        if int(dut.m_valid.value) and not ready:
            if held is not None:
                assert current == held
            held = current
        else:
            held = None
        in_fire = int(dut.s_valid.value) and int(dut.s_ready.value)
        out_fire = int(dut.m_valid.value) and ready
        await RisingEdge(dut.clk)
        if in_fire:
            sent += 1
        if out_fire:
            received.append(current)
        if len(received) == len(expected):
            break
    assert sent == len(items)
    assert received == expected
