# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def mailbox_commands_errors_and_backpressure(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.cmd_valid.value = 0
    dut.rsp_ready.value = 0
    dut.cmd_opcode.value = 0
    dut.cmd_argument.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    commands = [
        (0, 99, 0, 0, 0),
        (1, 0x12345678, 0x12345678, 0, 0),
        (2, 0xFFFFFFFE, 0xFFFFFFFE, 0, 0xFFFFFFFE),
        (2, 5, 3, 0, 3),
        (3, 0, 3, 0, 3),
        (0xA5, 0, 0xDEAD00A5, 1, 3),
        (4, 0, 0, 0, 0),
        (3, 0, 0, 0, 0),
    ]
    received = []
    for index, (opcode, argument, expected, error, accum) in enumerate(commands):
        while True:
            await FallingEdge(dut.clk)
            dut.rsp_ready.value = int(index % 3 != 1)
            dut.cmd_valid.value = 1
            dut.cmd_opcode.value = opcode
            dut.cmd_argument.value = argument
            await Timer(1, unit="ns")
            fire = int(dut.cmd_ready.value)
            await RisingEdge(dut.clk)
            if fire:
                break
        dut.cmd_valid.value = 0
        held = None
        for stall in range(6):
            await FallingEdge(dut.clk)
            dut.rsp_ready.value = int(stall >= (index % 3))
            await Timer(1, unit="ns")
            current = (int(dut.rsp_data.value), int(dut.rsp_error.value))
            if int(dut.rsp_valid.value) and not int(dut.rsp_ready.value):
                if held is not None:
                    assert current == held
                held = current
            fire = int(dut.rsp_valid.value) and int(dut.rsp_ready.value)
            await RisingEdge(dut.clk)
            if fire:
                received.append(current)
                break
        assert received[-1] == (expected, error)
        assert int(dut.accumulator.value) == accum
    assert len(received) == len(commands)
