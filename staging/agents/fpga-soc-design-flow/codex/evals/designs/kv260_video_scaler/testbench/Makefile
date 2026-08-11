# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(abspath ../reference/rtl/kv260_video_scaler.sv)
TOPLEVEL = kv260_video_scaler
MODULE = test_video_scaler
COMPILE_ARGS += -Wno-fatal
include $(shell cocotb-config --makefiles)/Makefile.sim
