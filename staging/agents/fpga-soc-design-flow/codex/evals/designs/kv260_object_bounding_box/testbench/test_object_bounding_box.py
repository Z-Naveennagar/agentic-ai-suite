# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer
@cocotb.test()
async def frame_bounding_boxes(dut):
 rng=random.Random(0x38);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
 dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0
 dut.s_foreground.value=0;dut.s_x.value=0;dut.s_y.value=0;dut.s_frame_first.value=0;dut.s_frame_last.value=0
 for _ in range(3): await RisingEdge(dut.clk)
 dut.rst_n.value=1
 masks=[
  (4,3,{(2,1)}),
  (5,4,{(0,0),(4,3),(2,2)}),
  (3,2,set()),
  (1,1,{(0,0)})
 ]
 items=[];expected=[]
 for width,height,fg in masks:
  for y in range(height):
   for x in range(width):
    items.append((int((x,y) in fg),x,y,int(x==0 and y==0),int(x==width-1 and y==height-1)))
  if fg:
   xs=[p[0] for p in fg];ys=[p[1] for p in fg];expected.append((1,min(xs),min(ys),max(xs),max(ys)))
  else: expected.append((0,0,0,0,0))
 sent=0;got=[];held=None
 for _ in range(5000):
  await FallingEdge(dut.clk);ready=rng.randrange(3)!=0;dut.m_ready.value=ready
  if sent<len(items):
   fg,x,y,first,last=items[sent];dut.s_valid.value=1;dut.s_foreground.value=fg;dut.s_x.value=x;dut.s_y.value=y;dut.s_frame_first.value=first;dut.s_frame_last.value=last
  else: dut.s_valid.value=0
  await Timer(1,unit="ns");now=(int(dut.m_found.value),int(dut.m_x_min.value),int(dut.m_y_min.value),int(dut.m_x_max.value),int(dut.m_y_max.value))
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
