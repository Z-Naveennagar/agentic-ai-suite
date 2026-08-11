# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG = verilog
CANDIDATE_DIR ?= $(abspath ../reference)
VERILOG_SOURCES = $(CANDIDATE_DIR)/rtl/kv260_i2s_receiver.sv
TOPLEVEL = kv260_i2s_receiver
COCOTB_TEST_MODULES = test_kv260_i2s_receiver
include $(shell cocotb-config --makefiles)/Makefile.sim
