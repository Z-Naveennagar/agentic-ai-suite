# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def signed_65(value):
    return value - (1 << 65) if value & (1 << 64) else value


@cocotb.test()
async def correlate_independent_timestamp_channels(dut):
    rng = random.Random(0x43)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.v_valid.value = 0
    dut.a_valid.value = 0
    dut.m_ready.value = 0
    dut.v_timestamp.value = 0
    dut.a_timestamp.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    pairs = [(100, 100), (500, 480), (900, 950), (0, (1 << 64) - 1)]
    pairs += [(rng.randrange(1 << 40), rng.randrange(1 << 40)) for _ in range(24)]
    video_index = 0
    audio_index = 0
    received = []
    held = None
    for _ in range(4000):
        await FallingEdge(dut.clk)
        ready = rng.randrange(3) != 0
        dut.m_ready.value = ready
        drive_video = video_index < len(pairs) and rng.randrange(3) != 0
        drive_audio = audio_index < len(pairs) and rng.randrange(3) != 0
        dut.v_valid.value = drive_video
        dut.a_valid.value = drive_audio
        if drive_video:
            dut.v_timestamp.value = pairs[video_index][0]
        if drive_audio:
            dut.a_timestamp.value = pairs[audio_index][1]
        await Timer(1, unit="ns")
        now = (
            int(dut.m_video_timestamp.value),
            int(dut.m_audio_timestamp.value),
            signed_65(int(dut.m_skew.value)),
        )
        if int(dut.m_valid.value) and not ready:
            if held is not None:
                assert now == held
            held = now
        else:
            held = None
        v_fire = drive_video and int(dut.v_ready.value)
        a_fire = drive_audio and int(dut.a_ready.value)
        out_fire = int(dut.m_valid.value) and ready
        await RisingEdge(dut.clk)
        if v_fire:
            video_index += 1
        if a_fire:
            audio_index += 1
        if out_fire:
            received.append(now)
        if len(received) == len(pairs):
            break
    expected = [(video, audio, video - audio) for video, audio in pairs]
    assert received == expected
