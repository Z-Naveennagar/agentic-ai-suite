#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""
add_license_headers.py -- Idempotently add the AMD MIT copyright header to source
and documentation files.

Reusable across skill check-in batches for the agentic-ai-suite repo.

Behavior:
  * Skips any file that already contains "SPDX-License-Identifier" (idempotent).
  * Markdown/HTML/XML/SVG use an HTML comment block. For Markdown that begins with
    YAML frontmatter ("---"), the block is inserted AFTER the closing "---" (matching
    the skills/hls-architect/SKILL.md reference); otherwise at the very top.
  * Script-style files (.py/.tcl/.sh/.yaml/.yml/.cfg/.mk) use "# " line comments,
    inserted after a shebang line if present.
  * C-style files (.c/.cpp/.h/.hpp/.v/.sv/.vh/.svh/.vhd/.vhdl/.xdc) use "// " lines.
  * Unknown or binary extensions (png/ttf/xlsx/pptx/jpeg/jpg/wdp/csv/json/xsd/rels/
    xlsx/gif/webp/pdf, etc.) are skipped.

Usage:
  python tools/add_license_headers.py <path> [<path> ...]
  python tools/add_license_headers.py --check <path>   # dry-run, exit 1 if any file needs a header
"""
import sys
import os

YEAR = "2026"
LINE1 = f"Copyright (C) {YEAR}, Advanced Micro Devices, Inc. All rights reserved."
LINE2 = "SPDX-License-Identifier: MIT"
MARKER = "SPDX-License-Identifier"

# Extension -> comment style
HTML_EXTS = {".md", ".markdown", ".html", ".htm", ".xml", ".svg"}
HASH_EXTS = {".py", ".tcl", ".sh", ".bash", ".yaml", ".yml", ".cfg", ".mk", ".toml", ".ini"}
SLASH_EXTS = {".c", ".cpp", ".cc", ".h", ".hpp", ".v", ".sv", ".vh", ".svh",
              ".vhd", ".vhdl", ".xdc"}
# Block-comment (/* ... */) style, e.g. GNU linker scripts.
BLOCK_EXTS = {".ld"}

# Extensions we deliberately never touch (binary / generated / data)
SKIP_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".pdf",
             ".ttf", ".otf", ".woff", ".woff2", ".xlsx", ".xls", ".pptx", ".ppt",
             ".docx", ".doc", ".wdp", ".csv", ".json", ".xsd", ".rels", ".zip",
             ".gz", ".tar", ".bin", ".dcp", ".pdi", ".bit", ".elf"}


def html_block():
    return f"<!--\n{LINE1}\n{LINE2}\n-->\n"


def hash_block():
    return f"# {LINE1}\n# {LINE2}\n"


def slash_block():
    return f"// {LINE1}\n// {LINE2}\n"


def cblock_block():
    return f"/*\n * {LINE1}\n * {LINE2}\n */\n"


def build_content(path, original):
    ext = os.path.splitext(path)[1].lower()
    if ext in HTML_EXTS:
        # frontmatter-aware for markdown
        lines = original.splitlines(keepends=True)
        if lines and lines[0].strip() == "---":
            # find closing --- of frontmatter
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    head = "".join(lines[: i + 1])
                    rest = "".join(lines[i + 1 :])
                    rest = rest.lstrip("\n")
                    return f"{head}\n{html_block()}\n{rest}"
            # no closing fence found -> treat as top insert
        return f"{html_block()}\n{original}"
    if ext in HASH_EXTS:
        lines = original.splitlines(keepends=True)
        if lines and lines[0].startswith("#!"):
            return lines[0] + hash_block() + "".join(lines[1:])
        return hash_block() + original
    if ext in SLASH_EXTS:
        return slash_block() + original
    if ext in BLOCK_EXTS:
        return cblock_block() + original
    return None  # unhandled -> skip


def process_file(path, check):
    ext = os.path.splitext(path)[1].lower()
    if ext in SKIP_EXTS:
        return "skip-binary"
    try:
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
    except (UnicodeDecodeError, OSError):
        return "skip-binary"
    if MARKER in original:
        return "already"
    new = build_content(path, original)
    if new is None:
        return "skip-unhandled"
    if check:
        return "would-add"
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return "added"


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        else:
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
                for name in files:
                    yield os.path.join(root, name)


def main(argv):
    check = False
    args = []
    for a in argv:
        if a == "--check":
            check = True
        else:
            args.append(a)
    if not args:
        print(__doc__)
        return 2
    counts = {}
    would = []
    for path in iter_files(args):
        result = process_file(path, check)
        counts[result] = counts.get(result, 0) + 1
        if result in ("added", "would-add"):
            would.append(path)
    verb = "would add" if check else "added"
    print(f"Header {verb}: {counts.get('would-add', 0) + counts.get('added', 0)}")
    print(f"Already had header: {counts.get('already', 0)}")
    print(f"Skipped (binary/unhandled): {counts.get('skip-binary', 0) + counts.get('skip-unhandled', 0)}")
    for w in would:
        print(f"  {verb}: {w}")
    if check and would:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
