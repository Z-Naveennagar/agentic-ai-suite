# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG = verilog
CANDIDATE_DIR ?= $(abspath ../reference)
VERILOG_SOURCES = $(CANDIDATE_DIR)/rtl/kv260_audio_gain.sv
TOPLEVEL = kv260_audio_gain
COCOTB_TEST_MODULES = test_kv260_audio_gain
include $(shell cocotb-config --makefiles)/Makefile.sim
