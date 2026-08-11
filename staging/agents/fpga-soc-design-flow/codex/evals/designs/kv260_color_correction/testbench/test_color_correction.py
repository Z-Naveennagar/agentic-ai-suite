# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer
def clip(x): return max(0,min(255,x))
def model(x):
    r=(x>>16)&255;g=(x>>8)&255;b=x&255
    return (clip((144*r-16*g+64)>>7)<<16)|(clip((-8*r+136*g+64)>>7)<<8)|clip((-16*g+144*b+64)>>7)
@cocotb.test()
async def matrix_saturation_and_stalls(dut):
    rng=random.Random(0x33);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
    dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0;dut.s_data.value=0;dut.s_user.value=0;dut.s_last.value=0
    for _ in range(3): await RisingEdge(dut.clk)
    dut.rst_n.value=1
    pixels=[0,0xffffff,0xff0000,0x00ff00,0x0000ff]+[rng.randrange(1<<24) for _ in range(100)]
    expected=[(model(x),int(i==0),int(i%19==18)) for i,x in enumerate(pixels)]
    sent=0;got=[];held=None
    for _ in range(4000):
        await FallingEdge(dut.clk);ready=rng.randrange(4)!=0;dut.m_ready.value=ready
        if sent<len(pixels):
            dut.s_valid.value=1;dut.s_data.value=pixels[sent];dut.s_user.value=int(sent==0);dut.s_last.value=int(sent%19==18)
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
