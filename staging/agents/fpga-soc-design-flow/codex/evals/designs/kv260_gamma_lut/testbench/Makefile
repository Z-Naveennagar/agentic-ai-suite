# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG := verilog
CANDIDATE_DIR ?= ../reference
VERILOG_SOURCES := $(abspath $(CANDIDATE_DIR)/rtl/kv260_gamma_lut.sv)
TOPLEVEL := kv260_gamma_lut
COCOTB_TEST_MODULES := test_gamma_lut
COMPILE_ARGS += -Wno-fatal
include $(shell cocotb-config --makefiles)/Makefile.sim
