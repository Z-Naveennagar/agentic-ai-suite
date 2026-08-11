# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(abspath ../reference/rtl/kv260_mipi_capture_pipeline.sv)
TOPLEVEL = kv260_mipi_capture_pipeline
MODULE = test_mipi_capture_pipeline
COMPILE_ARGS += -Wno-fatal
include $(shell cocotb-config --makefiles)/Makefile.sim
