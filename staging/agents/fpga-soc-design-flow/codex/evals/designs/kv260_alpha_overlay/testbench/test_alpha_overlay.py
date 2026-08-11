# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer
def model(fg,bg,a):
 out=0
 for shift in (16,8,0):
  c=(a*((fg>>shift)&255)+(255-a)*((bg>>shift)&255)+127)//255
  out|=c<<shift
 return out
@cocotb.test()
async def alpha_endpoints_rounding_and_stalls(dut):
 rng=random.Random(0x39);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
 dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0;dut.s_foreground.value=0;dut.s_background.value=0;dut.s_alpha.value=0;dut.s_user.value=0;dut.s_last.value=0
 for _ in range(3): await RisingEdge(dut.clk)
 dut.rst_n.value=1
 items=[(0xff0000,0x0000ff,0),(0xff0000,0x0000ff,255),(0xffffff,0,128)]
 items += [(rng.randrange(1<<24),rng.randrange(1<<24),rng.randrange(256)) for _ in range(120)]
 expected=[(model(f,b,a),int(i==0),int(i%29==28)) for i,(f,b,a) in enumerate(items)]
 sent=0;got=[];held=None
 for _ in range(5000):
  await FallingEdge(dut.clk);ready=rng.randrange(4)!=0;dut.m_ready.value=ready
  if sent<len(items):
   f,b,a=items[sent];dut.s_valid.value=1;dut.s_foreground.value=f;dut.s_background.value=b;dut.s_alpha.value=a;dut.s_user.value=int(sent==0);dut.s_last.value=int(sent%29==28)
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
