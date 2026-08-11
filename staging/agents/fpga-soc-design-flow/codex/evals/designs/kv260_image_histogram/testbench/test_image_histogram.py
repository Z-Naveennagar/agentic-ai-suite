# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer
@cocotb.test()
async def bins_total_and_clear(dut):
    rng=random.Random(0x35);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
    dut.rst_n.value=0;dut.clear.value=0;dut.s_valid.value=0;dut.s_data.value=0;dut.query_bin.value=0
    for _ in range(3): await RisingEdge(dut.clk)
    dut.rst_n.value=1
    pixels=list(range(0,256,17))+[rng.randrange(256) for _ in range(500)]
    counts=[0]*16
    for x in pixels:
        await FallingEdge(dut.clk);dut.s_valid.value=1;dut.s_data.value=x
        await RisingEdge(dut.clk);counts[x>>4]+=1
    await FallingEdge(dut.clk);dut.s_valid.value=0
    for b,want in enumerate(counts):
        dut.query_bin.value=b;await Timer(1,unit="ns");assert int(dut.query_count.value)==want
    assert int(dut.total_count.value)==len(pixels)
    dut.clear.value=1;await RisingEdge(dut.clk);await FallingEdge(dut.clk);dut.clear.value=0
    assert int(dut.total_count.value)==0
    for b in range(16):
        dut.query_bin.value=b;await Timer(1,unit="ns");assert int(dut.query_count.value)==0
