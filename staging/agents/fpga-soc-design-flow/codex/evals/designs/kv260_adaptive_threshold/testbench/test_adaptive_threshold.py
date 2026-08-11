# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer
@cocotb.test()
async def adaptive_threshold_edges(dut):
 rng=random.Random(0x36);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
 dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0
 dut.s_pixel.value=0;dut.s_mean.value=0;dut.threshold_offset.value=0;dut.s_user.value=0;dut.s_last.value=0
 for _ in range(3): await RisingEdge(dut.clk)
 dut.rst_n.value=1
 items=[(0,0,0),(10,10,0),(10,11,1),(255,255,255),(0,255,255)]
 items += [(rng.randrange(256),rng.randrange(256),rng.randrange(256)) for _ in range(120)]
 expected=[(255 if p+o>m else 0,int(i==0),int(i%23==22)) for i,(p,m,o) in enumerate(items)]
 sent=0;got=[];held=None
 for _ in range(5000):
  await FallingEdge(dut.clk);ready=rng.randrange(4)!=0;dut.m_ready.value=ready
  if sent<len(items):
   p,m,o=items[sent];dut.s_valid.value=1;dut.s_pixel.value=p;dut.s_mean.value=m;dut.threshold_offset.value=o
   dut.s_user.value=int(sent==0);dut.s_last.value=int(sent%23==22)
  else: dut.s_valid.value=0
  await Timer(1,unit="ns");now=(int(dut.m_mask.value),int(dut.m_user.value),int(dut.m_last.value))
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
