# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import zlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset_dut(dut):
    dut.rst.value = 1
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    dut.crc_ready.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0


async def send_byte(dut, value, last, rng):
    for _ in range(rng.randrange(4)):
        dut.s_axis_tvalid.value = 0
        await RisingEdge(dut.clk)
    dut.s_axis_tdata.value = value
    dut.s_axis_tlast.value = last
    dut.s_axis_tvalid.value = 1
    while True:
        await RisingEdge(dut.clk)
        if int(dut.s_axis_tready.value):
            break
    dut.s_axis_tvalid.value = 0


async def receive_crc(dut, expected, rng):
    held = None
    for _ in range(200):
        dut.crc_ready.value = rng.randrange(3) == 0
        await Timer(1, unit="ns")
        if int(dut.crc_valid.value):
            current = int(dut.crc_data.value)
            assert current == expected
            if not int(dut.crc_ready.value):
                if held is not None:
                    assert current == held, "CRC changed during result backpressure"
                held = current
            else:
                await RisingEdge(dut.clk)
                dut.crc_ready.value = 0
                return
        await RisingEdge(dut.clk)
    raise AssertionError("timed out waiting for CRC result")


@cocotb.test()
async def crc32_frames_and_backpressure(dut):
    rng = random.Random(0xC32)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    frames = [
        b"123456789",
        bytes([0]),
        bytes(range(32)),
        bytes(rng.getrandbits(8) for _ in range(127)),
    ]
    assert zlib.crc32(frames[0]) == 0xCBF43926

    for frame in frames:
        for index, byte in enumerate(frame):
            await send_byte(dut, byte, index == len(frame) - 1, rng)
        await receive_crc(dut, zlib.crc32(frame) & 0xFFFFFFFF, rng)

    dut.crc_ready.value = 0
    await send_byte(dut, 0xA5, 1, rng)
    for _ in range(5):
        await RisingEdge(dut.clk)
        assert int(dut.crc_valid.value) == 1
        assert int(dut.s_axis_tready.value) == 0
