# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def tick(dut):
    await RisingEdge(dut.s_axi_aclk)
    await Timer(1, unit="ns")


async def complete_ready_valid_handshake(dut, ready, channel, max_cycles=32):
    """Observe READY before the active edge, then consume that edge.

    Sampling READY only after RisingEdge can miss a legal handshake when the
    slave drops a combinational READY immediately after accepting VALID.
    """
    for _ in range(max_cycles):
        await Timer(1, unit="ns")
        if int(ready.value):
            await RisingEdge(dut.s_axi_aclk)
            await Timer(1, unit="ns")
            return
        await RisingEdge(dut.s_axi_aclk)
    raise AssertionError(f"timeout waiting for {channel} READY handshake")


async def wait_asserted(dut, signal, name, max_cycles=32):
    for _ in range(max_cycles):
        await Timer(1, unit="ns")
        if int(signal.value):
            return
        await RisingEdge(dut.s_axi_aclk)
    raise AssertionError(f"timeout waiting for {name} assertion")


async def write_aw_then_w(dut, addr, data, strobe=0xF):
    dut.s_axi_awaddr.value = addr
    dut.s_axi_awvalid.value = 1
    await complete_ready_valid_handshake(dut, dut.s_axi_awready, "AW")
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wdata.value = data
    dut.s_axi_wstrb.value = strobe
    dut.s_axi_wvalid.value = 1
    await complete_ready_valid_handshake(dut, dut.s_axi_wready, "W")
    dut.s_axi_wvalid.value = 0
    await wait_asserted(dut, dut.s_axi_bvalid, "BVALID")
    response = int(dut.s_axi_bresp.value)
    dut.s_axi_bready.value = 1
    await tick(dut)
    dut.s_axi_bready.value = 0
    return response


async def read(dut, addr):
    dut.s_axi_araddr.value = addr
    dut.s_axi_arvalid.value = 1
    await complete_ready_valid_handshake(dut, dut.s_axi_arready, "AR")
    dut.s_axi_arvalid.value = 0
    await wait_asserted(dut, dut.s_axi_rvalid, "RVALID")
    result = int(dut.s_axi_rdata.value), int(dut.s_axi_rresp.value)
    dut.s_axi_rready.value = 1
    await tick(dut)
    dut.s_axi_rready.value = 0
    return result


@cocotb.test()
async def register_access_strobes_and_errors(dut):
    cocotb.start_soon(Clock(dut.s_axi_aclk, 10, unit="ns").start())
    for signal in ("s_axi_awvalid", "s_axi_wvalid", "s_axi_bready",
                   "s_axi_arvalid", "s_axi_rready"):
        getattr(dut, signal).value = 0
    dut.s_axi_awaddr.value = 0
    dut.s_axi_wdata.value = 0
    dut.s_axi_wstrb.value = 0
    dut.s_axi_araddr.value = 0
    dut.s_axi_aresetn.value = 0
    await tick(dut)
    await tick(dut)
    dut.s_axi_aresetn.value = 1

    assert await write_aw_then_w(dut, 4, 0x11223344) == 0
    assert await read(dut, 4) == (0x11223344, 0)
    assert await write_aw_then_w(dut, 4, 0xAABBCCDD, 0b0101) == 0
    assert await read(dut, 4) == (0x11BB33DD, 0)
    assert await write_aw_then_w(dut, 2, 0xFFFFFFFF) == 2
    assert await read(dut, 0x20) == (0, 2)
