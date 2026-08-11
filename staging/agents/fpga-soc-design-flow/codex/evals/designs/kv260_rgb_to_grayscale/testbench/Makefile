# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(abspath ../reference/rtl/kv260_rgb_to_grayscale.sv)
TOPLEVEL = kv260_rgb_to_grayscale
MODULE = test_rgb_to_grayscale
COMPILE_ARGS += -Wno-fatal
include $(shell cocotb-config --makefiles)/Makefile.sim
