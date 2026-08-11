# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer
@cocotb.test()
async def exhaustive_gamma_table(dut):
    rng=random.Random(0x34);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
    dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0;dut.s_data.value=0;dut.s_user.value=0;dut.s_last.value=0
    for _ in range(3): await RisingEdge(dut.clk)
    dut.rst_n.value=1
    expected=[((x*x+255)>>8,int(x==0),int(x%32==31)) for x in range(256)]
    sent=0;got=[];held=None
    for _ in range(8000):
        await FallingEdge(dut.clk);ready=rng.randrange(5)!=0;dut.m_ready.value=ready
        if sent<256:
            dut.s_valid.value=rng.randrange(6)!=0;dut.s_data.value=sent;dut.s_user.value=int(sent==0);dut.s_last.value=int(sent%32==31)
        else: dut.s_valid.value=0
        await Timer(1,unit="ns");now=(int(dut.m_data.value),int(dut.m_user.value),int(dut.m_last.value))
        if int(dut.m_valid.value) and not ready:
            if held is not None: assert now==held
            held=now
        else: held=None
        infire=int(dut.s_valid.value) and int(dut.s_ready.value);outfire=int(dut.m_valid.value) and ready
        await RisingEdge(dut.clk)
        if infire: sent+=1
        if outfire: got.append(now)
        if len(got)==len(expected): break
    assert got==expected
