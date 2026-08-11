# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer
@cocotb.test()
async def exhaustive_erosion_dilation(dut):
 rng=random.Random(0x37);cocotb.start_soon(Clock(dut.clk,10,unit="ns").start())
 dut.rst_n.value=0;dut.s_valid.value=0;dut.m_ready.value=0;dut.s_window.value=0;dut.s_dilate.value=0;dut.s_user.value=0;dut.s_last.value=0
 for _ in range(3): await RisingEdge(dut.clk)
 dut.rst_n.value=1
 items=[(w,mode) for mode in (0,1) for w in range(512)]
 expected=[(int((w!=0) if mode else (w==511)),int(i==0),int(i%64==63)) for i,(w,mode) in enumerate(items)]
 sent=0;got=[];held=None
 for _ in range(20000):
  await FallingEdge(dut.clk);ready=rng.randrange(5)!=0;dut.m_ready.value=ready
  if sent<len(items):
   w,mode=items[sent];dut.s_valid.value=1;dut.s_window.value=w;dut.s_dilate.value=mode;dut.s_user.value=int(sent==0);dut.s_last.value=int(sent%64==63)
  else: dut.s_valid.value=0
  await Timer(1,unit="ns");now=(int(dut.m_pixel.value),int(dut.m_user.value),int(dut.m_last.value))
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
