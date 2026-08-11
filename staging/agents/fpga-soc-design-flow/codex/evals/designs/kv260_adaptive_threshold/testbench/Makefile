# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG := verilog
CANDIDATE_DIR ?= ../reference
VERILOG_SOURCES := $(abspath $(CANDIDATE_DIR)/rtl/kv260_adaptive_threshold.sv)
TOPLEVEL := kv260_adaptive_threshold
COCOTB_TEST_MODULES := test_adaptive_threshold
COMPILE_ARGS += -Wno-fatal
include $(shell cocotb-config --makefiles)/Makefile.sim
