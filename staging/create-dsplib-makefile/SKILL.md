---
name: create-dsplib-makefile
description: Use this skill to create the Makefile required for a DSPLib project created from the create-dsplib-graph skill
author: Florent Werbrouck
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Create DSPLib Makefile

Use this skill to create the Makefile required for for a DSPLib project created from the create-dsplib-graph skill

## Workflow Steps

1. Create Default Makefile

## Create Default Makefile

* Create the Makefile using the template below.
* Only edit the header comment and the following variables in the Makefile: PART_USE, AIE_APP, XILINX_VITIS and DSPLIB_ROOT
* AIE_APP variable in the Makefile should point to the graph application created by the `create-dsplib-graph` skill.
* PART_USE variable in the Makefile should be set to the part specified by the user. If user is targetting a vck190 set to `xcvc1902-vsva2197-2MP-e-S`, ff user is targetting a vek280 set to `xcve2802-vsvh1760-2MP-e-S`.
* DSPLIB_ROOT variable in the Makefile should be set to the root directory of the DSPLib library.

Create `Makefile`  where KERNEL refers to the name of the AI Engine kernel.

```
# Makefile for fft_2048 — 2048-point FFT on VEK280 (AIE-ML) 

# ============================================================
# Configuration
# ============================================================
PART_USE  		:= xcvc1902-vsva2197-2MP-e-S
DSPLIB_ROOT 	?= /Vitis_Libraries/dsp
AIE_APP 			:= src/graph.cpp
XILINX_VITIS 	?= /proj/gsd/vivado/2025.2/Vitis

# ============================================================
# Tools
# ============================================================
# Set Vitis environment if aiecompiler is not already on PATH
ifeq ($(shell which aiecompiler 2>/dev/null),)
  export XILINX_VITIS
  export PATH := $(XILINX_VITIS)/bin:$(XILINX_VITIS)/aietools/bin:$(PATH)
endif

VPP    := v++
AIECC  := ${VPP} -c --mode aie
AIESIM := aiesimulator
X86SIM := x86simulator

# ============================================================
# DSPLib include paths
# ============================================================
DSPLIB_INCL 	  := --include=${DSPLIB_ROOT}/L2/include/aie \
		               --include=${DSPLIB_ROOT}/L1/include/aie \
		               --include=${DSPLIB_ROOT}/L1/src/aie

# ============================================================
# AIE compiler flags
# ============================================================
AIE_FLAGS         	:= ${DSPLIB_INCL} \
											--part=${PART_USE} \
											--include=$(CURDIR)/src \
											$(CURDIR)/${AIE_APP}

# ============================================================
# AIE Simulation flags
# ============================================================
AIE_SIM_FLAGS       := --hang-detect-time=500000

# ============================================================
# Build outputs
# ============================================================
X86COM_OUTPUT				:= build/x86sim/libadf.a
AIECOM_OUTPUT       := build/hw/libadf.a


# ============================================================
# Targets
# ============================================================
${X86COM_OUTPUT}: x86com

.PHONY: all help clean x86com x86sim com sim

help::
	$(ECHO) "Makefile Usage:"
	$(ECHO) "  make all"
	$(ECHO) "    Command to generate the design targetting aiesimulator"
	$(ECHO) "  make com"
	$(ECHO) "    Command to generate the design targetting aiesimulator"
	$(ECHO) "  make sim"
	$(ECHO) "    Command to simulate the design using the aiesimulator"
	$(ECHO) "  make x86com"
	$(ECHO) "    Command to generate the design targetting x86simulator"
	$(ECHO) "  make x86sim"
	$(ECHO) "    Command to simulate the design using the x86simulator"

all: ${AIE_OUTPUT}

com: ${AIE_OUTPUT}

${AIE_OUTPUT}: ${AIE_APP}
	mkdir -p build/hw
	cd build/hw && v++ --compile --mode aie --target=hw ${AIE_FLAGS} |& tee log

sim: ${AIE_OUTPUT}
	cd build/hw && aiesimulator ${AIE_SIM_FLAGS} |& tee -a log

x86com:
  mkdir -p build/x86sim
	cd build/x86sim && ${AIECC} --target=x86sim ${AIE_FLAGS} |& tee log

x86sim: ${X86COM_OUTPUT}
	cd build/x86sim && x86simulator |& tee -a log

clean:
	rm -rf build log
```
