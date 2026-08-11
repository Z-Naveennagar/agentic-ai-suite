# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG := verilog
VERILOG_SOURCES := $(CANDIDATE_DIR)/rtl/pulse_counter.sv
TOPLEVEL := pulse_counter
COCOTB_TEST_MODULES := test_pulse_counter

include $(shell cocotb-config --makefiles)/Makefile.sim
