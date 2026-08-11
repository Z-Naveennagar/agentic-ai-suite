#!/usr/bin/env bash
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# vitis_env.sh — Verify a Vitis installation path and print resolved env vars.
#
# Usage:
#   source vitis_env.sh <vitis_install_path>
#
# On success: prints VITIS_PATH, VITIS_PYTHON, VITIS_PYLIB to stdout and exits 0.
# On failure: prints error to stderr and exits 1.
#
# Example:
#   bash vitis_env.sh /proj/gsd/vivado/2025.2/Vitis

VITIS_PATH="${1}"

if [[ -z "${VITIS_PATH}" ]]; then
    echo "Usage: $0 <vitis_install_path>" >&2
    exit 1
fi

if [[ ! -f "${VITIS_PATH}/settings64.sh" ]]; then
    echo "ERROR: settings64.sh not found in '${VITIS_PATH}' — not a valid Vitis installation." >&2
    exit 1
fi

# Detect bundled Python (pick the newest version)
VITIS_PY_DIR=$(ls --color=never -d "${VITIS_PATH}/tps/lnx64/python-"*/ 2>/dev/null | sort -V | tail -1)
if [[ -z "${VITIS_PY_DIR}" ]]; then
    echo "ERROR: No bundled Python found under '${VITIS_PATH}/tps/lnx64/'." >&2
    exit 1
fi

VITIS_PYTHON="${VITIS_PY_DIR}bin/python3"
VITIS_PYLIB="${VITIS_PY_DIR}lib"

if [[ ! -x "${VITIS_PYTHON}" ]]; then
    echo "ERROR: Bundled Python not executable: ${VITIS_PYTHON}" >&2
    exit 1
fi

# Source Vitis settings and test the vitis Python module
source "${VITIS_PATH}/settings64.sh" 2>/dev/null

RESULT=$(LD_LIBRARY_PATH="${VITIS_PYLIB}:${LD_LIBRARY_PATH}" \
          PYTHONPATH="${VITIS_PATH}/cli:${VITIS_PATH}/cli/proto:${PYTHONPATH}" \
          "${VITIS_PYTHON}" -c "import vitis; print('OK')" 2>&1)

if [[ "${RESULT}" != "OK" ]]; then
    echo "ERROR: 'import vitis' failed: ${RESULT}" >&2
    exit 1
fi

# Print resolved vars for the caller to capture
echo "VITIS_PATH=${VITIS_PATH}"
echo "VITIS_PYTHON=${VITIS_PYTHON}"
echo "VITIS_PYLIB=${VITIS_PYLIB}"