# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

SIM ?= verilator
TOPLEVEL_LANG := verilog
VERILOG_SOURCES := $(CANDIDATE_DIR)/rtl/kv260_dma_loopback.sv
TOPLEVEL := kv260_dma_loopback
COCOTB_TEST_MODULES := test_kv260_dma_loopback

include $(shell cocotb-config --makefiles)/Makefile.sim
