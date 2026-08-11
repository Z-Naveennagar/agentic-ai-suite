# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer
@cocotb.test()
async def crop_rectangle_and_backpressure(dut):
 rng=random.Random(0x40);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
 dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0;dut.s_data.value=0;dut.s_x.value=0;dut.s_y.value=0
 dut.crop_x0.value=2;dut.crop_y0.value=1;dut.crop_x1.value=6;dut.crop_y1.value=5
 for _ in range(3): await RisingEdge(dut.clk)
 dut.rst_n.value=1
 items=[(x,y,(y<<8)|x) for y in range(6) for x in range(8)]
 expected=[(d,int(x==2 and y==1),int(x==5)) for x,y,d in items if 2<=x<6 and 1<=y<5]
 sent=0;got=[];held=None
 for _ in range(5000):
  await FallingEdge(dut.clk);ready=rng.randrange(3)!=0;dut.m_ready.value=ready
  if sent<len(items):
   x,y,d=items[sent];dut.s_valid.value=1;dut.s_x.value=x;dut.s_y.value=y;dut.s_data.value=d
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
