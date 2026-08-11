# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG := verilog
VERILOG_SOURCES := $(CANDIDATE_DIR)/rtl/kv260_async_fifo.sv
TOPLEVEL := kv260_async_fifo
COCOTB_TEST_MODULES := test_kv260_async_fifo

COMPILE_ARGS += --Wno-MULTIDRIVEN

include $(shell cocotb-config --makefiles)/Makefile.sim
