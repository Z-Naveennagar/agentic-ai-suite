# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset_both(dut):
    dut.wr_rst.value = 1
    dut.rd_rst.value = 1
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.wr_data.value = 0
    for _ in range(5):
        await RisingEdge(dut.wr_clk)
    dut.wr_rst.value = 0
    for _ in range(4):
        await RisingEdge(dut.rd_clk)
    dut.rd_rst.value = 0


async def write_word(dut, value):
    dut.wr_data.value = value
    dut.wr_en.value = 1
    while True:
        await RisingEdge(dut.wr_clk)
        if not int(dut.full.value):
            break
    dut.wr_en.value = 0


async def read_word(dut):
    dut.rd_en.value = 1
    while True:
        await RisingEdge(dut.rd_clk)
        accepted = not int(dut.empty.value)
        if accepted:
            await Timer(1, unit="ns")
            value = int(dut.rd_data.value)
            dut.rd_en.value = 0
            return value


@cocotb.test()
async def ordered_dual_clock_fifo(dut):
    rng = random.Random(0xA5F1F0)
    cocotb.start_soon(Clock(dut.wr_clk, 10, unit="ns").start())
    cocotb.start_soon(Clock(dut.rd_clk, 14, unit="ns").start())
    await reset_both(dut)

    boundary = [0x1000 + index for index in range(16)]
    for value in boundary:
        await write_word(dut, value)
    for _ in range(8):
        await RisingEdge(dut.wr_clk)
        if int(dut.full.value):
            break
    assert int(dut.full.value) == 1
    for expected in boundary:
        assert await read_word(dut) == expected
    for _ in range(8):
        await RisingEdge(dut.rd_clk)
        if int(dut.empty.value):
            break
    assert int(dut.empty.value) == 1

    values = [rng.getrandbits(32) for _ in range(180)]

    async def producer():
        for value in values:
            for _ in range(rng.randrange(3)):
                await RisingEdge(dut.wr_clk)
            await write_word(dut, value)

    async def consumer():
        observed = []
        while len(observed) < len(values):
            for _ in range(rng.randrange(4)):
                await RisingEdge(dut.rd_clk)
            observed.append(await read_word(dut))
        return observed

    producer_task = cocotb.start_soon(producer())
    consumer_task = cocotb.start_soon(consumer())
    await producer_task
    observed = await consumer_task
    assert observed == values
