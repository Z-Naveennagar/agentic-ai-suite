# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def independent_pack_unpack_channels(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst_n.value = 0
    dut.s_cap_tvalid.value = 0
    dut.s_rd_tvalid.value = 0
    dut.m_wr_tready.value = 0
    dut.m_disp_tready.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    rng = random.Random(1703)
    cap = [(rng.randrange(1 << 24), int(i == 0), int(i % 9 == 8)) for i in range(63)]
    rd = [(rng.randrange(1 << 32), int(i == 0), int(i % 7 == 6)) for i in range(55)]
    cap_i = rd_i = 0
    wr_got, disp_got = [], []
    wr_held = disp_held = None

    for _ in range(3000):
        await FallingEdge(dut.clk)
        dut.m_wr_tready.value = rng.randrange(3) != 0
        dut.m_disp_tready.value = rng.randrange(4) != 0
        if cap_i < len(cap):
            data, user, last = cap[cap_i]
            dut.s_cap_tvalid.value = 1
            dut.s_cap_tdata.value = data
            dut.s_cap_tuser.value = user
            dut.s_cap_tlast.value = last
        else:
            dut.s_cap_tvalid.value = 0
        if rd_i < len(rd):
            data, user, last = rd[rd_i]
            dut.s_rd_tvalid.value = 1
            dut.s_rd_tdata.value = data
            dut.s_rd_tuser.value = user
            dut.s_rd_tlast.value = last
        else:
            dut.s_rd_tvalid.value = 0
        await Timer(1, units="ns")

        if dut.m_wr_tvalid.value:
            now = (int(dut.m_wr_tdata.value), int(dut.m_wr_tkeep.value), int(dut.m_wr_tuser.value), int(dut.m_wr_tlast.value))
            if dut.m_wr_tready.value:
                wr_got.append(now)
                wr_held = None
            else:
                if wr_held is not None:
                    assert now == wr_held
                wr_held = now
        if dut.m_disp_tvalid.value:
            now = (int(dut.m_disp_tdata.value), int(dut.m_disp_tuser.value), int(dut.m_disp_tlast.value))
            if dut.m_disp_tready.value:
                disp_got.append(now)
                disp_held = None
            else:
                if disp_held is not None:
                    assert now == disp_held
                disp_held = now
        if dut.s_cap_tvalid.value and dut.s_cap_tready.value:
            cap_i += 1
        if dut.s_rd_tvalid.value and dut.s_rd_tready.value:
            rd_i += 1
        await RisingEdge(dut.clk)
        if len(wr_got) == len(cap) and len(disp_got) == len(rd):
            break

    assert wr_got == [(d, 0xF, u, l) for d, u, l in cap]
    assert disp_got == [(d & 0xFFFFFF, u, l) for d, u, l in rd]
