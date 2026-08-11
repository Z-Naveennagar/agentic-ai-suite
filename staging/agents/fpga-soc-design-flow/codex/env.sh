#!/usr/bin/env bash
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT


FPGA_SOC_AGENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FPGA_SOC_AGENT_ROOT

if [[ -d "${FPGA_SOC_AGENT_ROOT}/.tools/verilator-5.050/bin" ]]; then
  export PATH="${FPGA_SOC_AGENT_ROOT}/.tools/verilator-5.050/bin:${PATH}"
fi
if [[ -d "${FPGA_SOC_AGENT_ROOT}/.venv/bin" ]]; then
  export PATH="${FPGA_SOC_AGENT_ROOT}/.venv/bin:${PATH}"
  export VIVADO_AGENT_PYTHON="${FPGA_SOC_AGENT_ROOT}/.venv/bin/python"
else
  export VIVADO_AGENT_PYTHON="$(command -v python3)"
fi
