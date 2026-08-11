#!/usr/bin/env bash
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# export-zip.sh — Produce a clean, history-free delivery zip of the
# public-facing skills, mirroring the copybara `publish-skills` workflow
# defined in copy.bara.sky (same include/exclude globs + text transform).
#
# Unlike copybara (which pushes to a git.destination repo), this packages
# the selected files into a zip for direct hand-off to users.
#
# It exports from the WORKING TREE (tracked files + new untracked files,
# honoring .gitignore), so you can iterate on source changes WITHOUT
# committing first. No .git metadata / history is ever included.
#
# Usage:
#   deploy/export-zip.sh [OUTPUT_DIR]
#
#   OUTPUT_DIR   Where to write the staged tree + zip (default: .tmp/export)
#
# Examples:
#   deploy/export-zip.sh                 # -> .tmp/export/agentic-ai-suite-YYYY-MM-DD.zip
#   deploy/export-zip.sh /path/to/out    # custom output location

set -euo pipefail

# --- Locate repo root (works regardless of where the script is invoked) ---
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# --- Config (keep in sync with deploy/copy.bara.sky) ----------------------
PKG_NAME="agentic-ai-suite"
OUT_DIR="${1:-$REPO_ROOT/.tmp/export}"
DATE="$(date +%Y-%m-%d)"
STAGE="$OUT_DIR/$PKG_NAME"
ZIP="$OUT_DIR/${PKG_NAME}-${DATE}.zip"

# origin_files -> include  (copy.bara.sky)
INCLUDE_PATHS=(skills examples docs README.md LICENSE)

# origin_files -> exclude  (any-depth dir names, mirroring copybara's
# "**/evals/**" and "**/testcases/**"). Top-level staging/tests/deploy/plugin
# are excluded by simply not being listed in INCLUDE_PATHS above — do NOT add
# "plugin" here: copybara only excludes a top-level plugin/ ("plugin/**"), so
# an any-depth match would wrongly drop a nested skills/*/plugin/ subdir.
# "staging" excludes docs/staging/ (PDF-only content not shipped to users).
EXCLUDE_NAMES=(evals testcases staging)

# transformations -> core.replace  (before -> after)
REPLACE_BEFORE='gitenterprise\.xilinx\.com'
REPLACE_AFTER='github.com'

# --- Clean staging ---------------------------------------------------------
rm -rf "$STAGE" "$ZIP"
mkdir -p "$STAGE"

# --- Collect deliverable files --------------------------------------------
# git ls-files --cached (tracked) + --others --exclude-standard (untracked but
# NOT git-ignored) gives exactly the deliverable set, reflecting uncommitted
# edits and newly added files while dropping .tmp/, __pycache__, *.pyc, etc.
copied=0
skipped=0
while IFS= read -r -d '' f; do
    # Apply nested exclude-name filter on any path component.
    skip=0
    for name in "${EXCLUDE_NAMES[@]}"; do
        case "/$f/" in
            */"$name"/*) skip=1; break ;;
        esac
    done
    if [ "$skip" -eq 1 ]; then
        skipped=$((skipped + 1))
        continue
    fi
    mkdir -p "$STAGE/$(dirname "$f")"
    cp -p "$f" "$STAGE/$f"
    copied=$((copied + 1))
done < <(git ls-files --cached --others --exclude-standard -z -- "${INCLUDE_PATHS[@]}")

if [ "$copied" -eq 0 ]; then
    echo "ERROR: no files matched the include set — nothing to package." >&2
    exit 1
fi

# --- Apply text transformation --------------------------------------------
transformed=0
mapfile -t tfiles < <(grep -rlZ "$REPLACE_BEFORE" "$STAGE" 2>/dev/null | tr '\0' '\n' || true)
if [ "${#tfiles[@]}" -gt 0 ] && [ -n "${tfiles[0]:-}" ]; then
    sed -i "s/${REPLACE_BEFORE}/${REPLACE_AFTER}/g" "${tfiles[@]}"
    transformed=${#tfiles[@]}
fi

# --- Verify no internal references leaked ----------------------------------
if grep -rn "$REPLACE_BEFORE" "$STAGE" >/dev/null 2>&1; then
    echo "ERROR: internal references still present after transform:" >&2
    grep -rn "$REPLACE_BEFORE" "$STAGE" >&2
    exit 1
fi

# --- Package ---------------------------------------------------------------
( cd "$OUT_DIR" && zip -r -q "$(basename "$ZIP")" "$PKG_NAME" )

# --- Report ----------------------------------------------------------------
files_total=$(find "$STAGE" -type f | wc -l)
dirs_total=$(find "$STAGE" -type d | wc -l)
zip_size=$(du -h "$ZIP" | cut -f1)

echo "-----------------------------------------------------------------------"
echo "Delivery package created (history-free, copybara publish-skills rules):"
echo "  zip:          $ZIP"
echo "  size:         $zip_size"
echo "  files:        $files_total  (dirs: $dirs_total)"
echo "  copied:       $copied   excluded(nested): $skipped"
echo "  transformed:  $transformed file(s)  ($REPLACE_BEFORE -> $REPLACE_AFTER)"
echo "  staged tree:  $STAGE"
echo "-----------------------------------------------------------------------"
