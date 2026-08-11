# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


async def launch_and_collect(dut, base, count, stride, write, rng):
    await FallingEdge(dut.clk)
    dut.base_address.value = base
    dut.beat_count.value = count
    dut.stride_bytes.value = stride
    dut.write_mode.value = write
    dut.start.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.start.value = 0
    if count == 0:
        assert int(dut.done.value) == 1
        assert int(dut.busy.value) == 0
        return []
    accepted = []
    held = None
    for cycle in range(1000):
        ready = int(rng.randrange(3) != 0)
        dut.req_ready.value = ready
        if cycle == 2:
            dut.start.value = 1
            dut.base_address.value = 0xDEAD0000
        else:
            dut.start.value = 0
        await Timer(1, unit="ns")
        item = (int(dut.req_address.value), int(dut.req_write.value))
        if int(dut.req_valid.value) and not ready:
            if held is not None:
                assert item == held
            held = item
        else:
            held = None
        fire = int(dut.req_valid.value) and ready
        await RisingEdge(dut.clk)
        if fire:
            accepted.append(item)
        await FallingEdge(dut.clk)
        if int(dut.done.value):
            break
    assert int(dut.issued_count.value) == count
    return accepted


@cocotb.test()
async def bounded_read_write_requests_with_stalls(dut):
    rng = random.Random(0x47)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.req_ready.value = 0
    dut.base_address.value = 0
    dut.beat_count.value = 0
    dut.stride_bytes.value = 0
    dut.write_mode.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    zero = await launch_and_collect(dut, 0x1000, 0, 4, 0, rng)
    assert zero == []
    reads = await launch_and_collect(dut, 0x2000, 17, 64, 0, rng)
    writes = await launch_and_collect(dut, 0x80000000, 11, 16, 1, rng)
    assert reads == [(0x2000 + 64 * index, 0) for index in range(17)]
    assert writes == [(0x80000000 + 16 * index, 1) for index in range(11)]
