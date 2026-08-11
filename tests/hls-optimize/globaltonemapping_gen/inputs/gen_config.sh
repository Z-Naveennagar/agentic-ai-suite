#!/bin/bash
#Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
#SPDX-License-Identifier: MIT
# Generate hls_config.cfg from template with OpenCV paths
# Headers are organized in ./include/ subdirectory

# Auto-detect OpenCV when the env vars are not set. This must NOT rely on the
# invoking shell's environment: the coding agent runs its shell commands inside
# a long-lived `opencode serve` daemon whose environment is whatever it was
# started with, so exporting OPENCV_* around `skills-test run` does NOT reliably
# reach the agent. Run 8c6d64c1 is what this guards against — the agent found no
# OpenCV, concluded the host lacked it, and rewrote the frozen testbench to drop
# the dependency instead of running the real flow.
# Explicit env vars still win; detection only fills in what is unset.
if [ -z "${OPENCV_INCLUDE:-}" ] || [ -z "${OPENCV_LIB:-}" ]; then
    # NOTE on the /home/*/ probe: $HOME is not reliably the invoking user's home
    # here (it is plain `/home` on this host), and a locally-built OpenCV is a
    # common way to satisfy this suite, so scan per-user prefixes explicitly.
    for _cv_root in \
        ${OPENCV_HOME:-} \
        "$HOME/.local/opt"/opencv-* \
        /home/*/.local/opt/opencv-* \
        /usr/local \
        /usr \
        /opt/opencv*; do
        [ -d "$_cv_root" ] || continue
        # headers land at <root>/include/opencv4/opencv2/opencv.hpp
        if [ -f "$_cv_root/include/opencv4/opencv2/opencv.hpp" ]; then
            _cv_inc="$_cv_root/include/opencv4"
        elif [ -f "$_cv_root/include/opencv2/opencv.hpp" ]; then
            _cv_inc="$_cv_root/include"
        else
            continue
        fi
        for _cv_libdir in "$_cv_root/lib" "$_cv_root/lib64" \
                          "$_cv_root/lib/x86_64-linux-gnu"; do
            if ls "$_cv_libdir"/libopencv_core.so* >/dev/null 2>&1; then
                OPENCV_INCLUDE="${OPENCV_INCLUDE:-$_cv_inc}"
                OPENCV_LIB="${OPENCV_LIB:-$_cv_libdir}"
                break
            fi
        done
        [ -n "${OPENCV_LIB:-}" ] && break
    done
    export OPENCV_INCLUDE OPENCV_LIB
    [ -n "${OPENCV_INCLUDE:-}" ] && echo "Auto-detected OpenCV: include=$OPENCV_INCLUDE lib=$OPENCV_LIB"
fi

if [ -z "${OPENCV_INCLUDE:-}" ] || [ -z "${OPENCV_LIB:-}" ]; then
    echo "Error: could not auto-detect OpenCV; set OPENCV_INCLUDE and OPENCV_LIB"
    echo "Example:"
    echo "  export OPENCV_INCLUDE=/usr/include/opencv4"
    echo "  export OPENCV_LIB=/usr/lib64"
    exit 1
fi

# Optional extra linker flags appended to csim/cosim/sim ldflags. Needed when
# the host's OpenCV requires a newer libstdc++ than the one Vitis bundles (Vitis
# 2025.1 ships GLIBCXX up to 3.4.25); pointing the link at the system libstdc++
# resolves it. Unset is fine -- envsubst expands it to nothing.
#   export OPENCV_LDFLAGS_EXTRA="/usr/lib/x86_64-linux-gnu/libstdc++.so.6 -Wl,-rpath,$OPENCV_LIB"
# Auto-detect the libstdc++ case as well: Vitis 2025.1 bundles GLIBCXX up to
# 3.4.25, and a system OpenCV built against a newer toolchain (e.g. needing
# GLIBCXX_3.4.30) then fails to link under csim/cosim. When the system
# libstdc++ is present and the OpenCV libs reference a GLIBCXX the Vitis one
# lacks, link against the system copy.
if [ -z "${OPENCV_LDFLAGS_EXTRA:-}" ]; then
    _sys_libstdcxx=/usr/lib/x86_64-linux-gnu/libstdc++.so.6
    if [ -f "$_sys_libstdcxx" ] && \
       ls "$OPENCV_LIB"/libopencv_core.so* >/dev/null 2>&1; then
        _need="$(strings "$OPENCV_LIB"/libopencv_core.so 2>/dev/null \
                 | grep -o 'GLIBCXX_[0-9.]*' | sort -V | tail -1)"
        _vitis_has="$(strings "${XILINX_VITIS:-}/lib/lnx64.o/Default/libstdc++.so.6" 2>/dev/null \
                 | grep -o 'GLIBCXX_[0-9.]*' | sort -V | tail -1)"
        if [ -n "$_need" ] && [ "$_need" != "$_vitis_has" ] && \
           [ "$(printf '%s\n%s\n' "$_need" "$_vitis_has" | sort -V | tail -1)" = "$_need" ]; then
            OPENCV_LDFLAGS_EXTRA="$_sys_libstdcxx -Wl,-rpath,$OPENCV_LIB"
            echo "Auto-detected libstdc++ mismatch (OpenCV needs $_need, Vitis has ${_vitis_has:-none})"
        fi
    fi
fi
export OPENCV_LDFLAGS_EXTRA="${OPENCV_LDFLAGS_EXTRA:-}"

echo "Generating hls_config.cfg..."
echo "  OPENCV_INCLUDE = $OPENCV_INCLUDE"
echo "  OPENCV_LIB = $OPENCV_LIB"
echo "  OPENCV_LDFLAGS_EXTRA = ${OPENCV_LDFLAGS_EXTRA:-<unset>}"
echo "  Local headers = ./include/"

# Set absolute path for test image
export PROJECT_DIR=$(pwd)
echo "  PROJECT_DIR = $PROJECT_DIR"

envsubst < hls_config.tmpl > hls_config.cfg

echo "Done. hls_config.cfg generated successfully."
