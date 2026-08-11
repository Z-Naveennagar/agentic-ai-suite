# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer

def pack(p): return sum(v<<(8*i) for i,v in enumerate(p))
def model(p,phase):
    if phase==0: r,g,b=p[4],sum(p[i] for i in (1,3,5,7))//4,sum(p[i] for i in (0,2,6,8))//4
    elif phase==1: r,g,b=(p[3]+p[5])//2,p[4],(p[1]+p[7])//2
    elif phase==2: r,g,b=(p[1]+p[7])//2,p[4],(p[3]+p[5])//2
    else: r,g,b=sum(p[i] for i in (0,2,6,8))//4,sum(p[i] for i in (1,3,5,7))//4,p[4]
    return (r<<16)|(g<<8)|b

@cocotb.test()
async def all_bayer_phases(dut):
    rng=random.Random(0x32);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
    dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0
    dut.s_data.value=0;dut.s_phase.value=0;dut.s_user.value=0;dut.s_last.value=0
    for _ in range(3): await RisingEdge(dut.clk)
    dut.rst_n.value=1
    vectors=[([10,20,30,40,50,60,70,80,90],q) for q in range(4)]
    vectors += [([rng.randrange(256) for _ in range(9)],rng.randrange(4)) for _ in range(96)]
    expected=[(model(p,q),int(i==0),int(i%17==16)) for i,(p,q) in enumerate(vectors)]
    sent=0;got=[];held=None
    for _ in range(4000):
        await FallingEdge(dut.clk);ready=rng.randrange(5)!=0;dut.m_ready.value=ready
        if sent<len(vectors):
            p,q=vectors[sent];dut.s_valid.value=1;dut.s_data.value=pack(p);dut.s_phase.value=q
            dut.s_user.value=int(sent==0);dut.s_last.value=int(sent%17==16)
        else: dut.s_valid.value=0
        await Timer(1,unit="ns")
        now=(int(dut.m_data.value),int(dut.m_user.value),int(dut.m_last.value))
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
