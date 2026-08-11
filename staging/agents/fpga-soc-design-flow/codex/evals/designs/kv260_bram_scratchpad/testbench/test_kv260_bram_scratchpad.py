# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def apply_bytes(old, new, enables):
    value = old
    for lane in range(4):
        if enables & (1 << lane):
            mask = 0xFF << (8 * lane)
            value = (value & ~mask) | (new & mask)
    return value


async def cycle(dut, model, a, b):
    await FallingEdge(dut.clk)
    for prefix, transaction in (("a", a), ("b", b)):
        enable, write_enable, address, data = transaction
        getattr(dut, f"{prefix}_en").value = enable
        getattr(dut, f"{prefix}_we").value = write_enable
        getattr(dut, f"{prefix}_addr").value = address
        getattr(dut, f"{prefix}_wdata").value = data
    expected_a = model[a[2]] if a[0] else None
    expected_b = model[b[2]] if b[0] else None
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    if expected_a is not None:
        assert int(dut.a_rdata.value) == expected_a
    if expected_b is not None:
        assert int(dut.b_rdata.value) == expected_b
    if a[0]:
        model[a[2]] = apply_bytes(model[a[2]], a[3], a[1])
    if b[0]:
        model[b[2]] = apply_bytes(model[b[2]], b[3], b[1])


@cocotb.test()
async def dual_port_read_first_and_collisions(dut):
    rng = random.Random(0xB2A4)
    model = [0] * 256
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    dut.a_en.value = 0
    dut.b_en.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0

    for address in range(256):
        await cycle(dut, model, (1, 0xF, address, 0), (0, 0, 0, 0))

    await cycle(
        dut,
        model,
        (1, 0b0011, 7, 0xAAAABBBB),
        (1, 0b1100, 7, 0xCCCCDDDD),
    )
    assert model[7] == 0xCCCCBBBB
    await cycle(
        dut,
        model,
        (1, 0b0101, 9, 0x11223344),
        (1, 0b0101, 9, 0xA1B2C3D4),
    )
    assert model[9] == 0x00B200D4

    for _ in range(400):
        address_a = rng.randrange(256)
        address_b = address_a if rng.randrange(5) == 0 else rng.randrange(256)
        transaction_a = (
            rng.randrange(5) != 0,
            rng.randrange(16),
            address_a,
            rng.getrandbits(32),
        )
        transaction_b = (
            rng.randrange(5) != 0,
            rng.randrange(16),
            address_b,
            rng.getrandbits(32),
        )
        await cycle(dut, model, transaction_a, transaction_b)
