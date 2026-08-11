# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def descriptor_fifo_order_wrap_and_completion(dut):
    rng = random.Random(0x46)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.push_valid.value = 0
    dut.pop_ready.value = 0
    dut.completion_valid.value = 0
    dut.push_address.value = 0
    dut.push_length.value = 0
    dut.push_tag.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    descriptors = [
        (0x10000000 + index * 0x1000, 64 + index * 7, index)
        for index in range(40)
    ]
    model = []
    sent = 0
    received = []
    completions = 0
    held = None
    saw_full = False
    saw_simultaneous = False
    for cycle in range(2000):
        await FallingEdge(dut.clk)
        pop_ready = int(cycle > 8 and rng.randrange(4) != 0)
        dut.pop_ready.value = pop_ready
        dut.completion_valid.value = int(cycle % 7 == 3)
        if cycle % 7 == 3:
            completions += 1
        if sent < len(descriptors) and rng.randrange(5) != 0:
            address, length, tag = descriptors[sent]
            dut.push_valid.value = 1
            dut.push_address.value = address
            dut.push_length.value = length
            dut.push_tag.value = tag
        else:
            dut.push_valid.value = 0
        await Timer(1, unit="ns")
        push_fire = int(dut.push_valid.value) and int(dut.push_ready.value)
        pop_fire = int(dut.pop_valid.value) and pop_ready
        output = (
            int(dut.pop_address.value),
            int(dut.pop_length.value),
            int(dut.pop_tag.value),
        )
        if int(dut.pop_valid.value) and not pop_ready:
            if held is not None:
                assert output == held
            held = output
        else:
            held = None
        if int(dut.queued_count.value) == 4:
            saw_full = True
        if push_fire and pop_fire:
            saw_simultaneous = True
        expected_pop = model[0] if pop_fire else None
        pushed = descriptors[sent] if push_fire else None
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if pop_fire:
            assert output == expected_pop
            received.append(model.pop(0))
        if push_fire:
            model.append(pushed)
            sent += 1
        assert int(dut.queued_count.value) == len(model)
        if sent == len(descriptors) and not model:
            break
    assert received == descriptors
    assert saw_full and saw_simultaneous
    assert int(dut.completion_count.value) == completions
