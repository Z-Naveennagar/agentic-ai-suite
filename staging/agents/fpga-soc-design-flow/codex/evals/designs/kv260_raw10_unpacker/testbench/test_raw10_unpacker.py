# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

def pack_raw10(p):
    return (p[0] >> 2) | ((p[1] >> 2) << 8) | ((p[2] >> 2) << 16) | ((p[3] >> 2) << 24) | ((p[0] & 3) << 32) | ((p[1] & 3) << 34) | ((p[2] & 3) << 36) | ((p[3] & 3) << 38)

@cocotb.test()
async def raw10_groups_backpressure(dut):
    rng=random.Random(0x31)
    cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
    dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0
    dut.s_data.value=0;dut.s_user.value=0;dut.s_last.value=0
    for _ in range(3): await RisingEdge(dut.clk)
    dut.rst_n.value=1
    groups=[[0,1,2,3],[1023,512,255,4]]+[[rng.randrange(1024) for _ in range(4)] for _ in range(80)]
    items=[(pack_raw10(p),int(i==0),int(i%13==12)) for i,p in enumerate(groups)]
    expected=[(sum(v<<(16*j) for j,v in enumerate(p)),u,l) for p,(_,u,l) in zip(groups,items)]
    sent=0;received=[];held=None
    for _ in range(3000):
        await FallingEdge(dut.clk)
        ready=rng.randrange(4)!=0;dut.m_ready.value=ready
        if sent<len(items):
            d,u,l=items[sent];dut.s_valid.value=1;dut.s_data.value=d;dut.s_user.value=u;dut.s_last.value=l
        else: dut.s_valid.value=0
        await Timer(1,unit="ns")
        now=(int(dut.m_data.value),int(dut.m_user.value),int(dut.m_last.value))
        if int(dut.m_valid.value) and not ready:
            if held is not None: assert now==held
            held=now
        else: held=None
        infire=int(dut.s_valid.value) and int(dut.s_ready.value)
        outfire=int(dut.m_valid.value) and ready
        await RisingEdge(dut.clk)
        if infire: sent+=1
        if outfire: received.append(now)
        if len(received)==len(expected): break
    assert received==expected
