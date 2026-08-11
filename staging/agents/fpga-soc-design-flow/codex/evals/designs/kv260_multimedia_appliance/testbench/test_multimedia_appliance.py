# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge


async def pulse(dut, name):
    await FallingEdge(dut.clk)
    getattr(dut, name).value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    getattr(dut, name).value = 0


async def start_run(dut, frames, audio):
    await FallingEdge(dut.clk)
    dut.target_frames.value = frames
    dut.target_audio_blocks.value = audio
    dut.start.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.start.value = 0


@cocotb.test()
async def nominal_zero_error_abort_and_clear(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for name in ("start", "clear", "frame_event", "audio_event",
                 "ddr_error", "abort", "target_frames",
                 "target_audio_blocks"):
        getattr(dut, name).value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    await start_run(dut, 0, 0)
    assert (int(dut.busy.value), int(dut.done.value),
            int(getattr(dut, "pass").value)) == (0, 1, 1)
    await pulse(dut, "clear")
    assert (int(dut.done.value), int(getattr(dut, "pass").value),
            int(dut.error_code.value)) == (0, 0, 0)

    await start_run(dut, 3, 2)
    assert int(dut.busy.value) == 1
    await pulse(dut, "frame_event")
    await pulse(dut, "audio_event")
    await FallingEdge(dut.clk)
    dut.start.value = 1
    dut.target_frames.value = 99
    dut.frame_event.value = 1
    dut.audio_event.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.start.value = 0
    dut.frame_event.value = 0
    dut.audio_event.value = 0
    assert int(dut.busy.value) == 1
    assert int(dut.frame_count.value) == 2
    assert int(dut.audio_count.value) == 2
    await pulse(dut, "frame_event")
    assert (int(dut.busy.value), int(dut.done.value),
            int(getattr(dut, "pass").value)) == (0, 1, 1)
    assert (int(dut.frame_count.value), int(dut.audio_count.value)) == (3, 2)

    await start_run(dut, 5, 5)
    await pulse(dut, "ddr_error")
    assert (int(dut.done.value), int(getattr(dut, "pass").value),
            int(dut.error_code.value)) == (1, 0, 1)
    await start_run(dut, 5, 5)
    await pulse(dut, "abort")
    assert (int(dut.done.value), int(getattr(dut, "pass").value),
            int(dut.error_code.value)) == (1, 0, 2)
    await pulse(dut, "clear")
    assert (int(dut.busy.value), int(dut.done.value),
            int(getattr(dut, "pass").value),
            int(dut.frame_count.value), int(dut.audio_count.value),
            int(dut.error_code.value)) == (0, 0, 0, 0, 0, 0)
