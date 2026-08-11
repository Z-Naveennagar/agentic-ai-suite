#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Build a single downloadable PDF guide from a set of mkdocs-material pages.

Usage:
    uvx --with markdown --with pymdown-extensions --with "weasyprint==52.5" \\
        python deploy/pdf/build_pdf.py <config.json>

    NOTE: weasyprint MUST be pinned to 52.5 in this environment. Newer
    versions (tested: 59.0, 66.0) crash with
    "AttributeError: function/symbol 'pango_context_set_round_glyph_positions'
    not found in library 'libpango-1.0.so.0'" because the system Pango
    library is old (1.42.3, RHEL8/CentOS8-era). Do not drop the pin.

The config JSON looks like:
{
  "title": "ChipScope MCP Server \u2014 Complete Guide",
  "subtitle": "AMD Embedded Agentic AI Suite \u2014 Early Access",
  "tab_name": "ChipScope",
  "output": "docs/chipscope/ChipScope-MCP-Server-Guide.pdf",
  "sources": [
    "docs/chipscope/index.md",
    "docs/chipscope/getting-started.md",
    "docs/chipscope/example-prompts.md",
    "docs/chipscope/tool-reference.md"
  ]
}

This is a template intended to be reused for other tabs (Vivado, Vitis HLS,
Local RAG, etc.) once the ChipScope pilot is validated.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

import markdown as md
from weasyprint import HTML

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

MKDOCS_EXTRA_RE = re.compile(r"^\s+([\w]+):\s+(.+)$")


def load_mkdocs_extra() -> dict:
    """Parse the `extra:` block from mkdocs.yml, if present."""
    yml_path = REPO_ROOT / "mkdocs.yml"
    if not yml_path.exists():
        return {}
    yml = yml_path.read_text(encoding="utf-8")
    extra = {}
    in_extra = False
    for line in yml.splitlines():
        if re.match(r"^extra:\s*$", line):
            in_extra = True
            continue
        if in_extra:
            m = MKDOCS_EXTRA_RE.match(line)
            if m:
                extra[m.group(1)] = m.group(2).strip()
            elif not line.startswith(" "):
                break
    return extra


def expand_macros(text: str, macros: dict) -> str:
    """Replace Jinja-style {{ var }} with values from the macros dict."""
    for key, value in macros.items():
        text = text.replace("{{ " + key + " }}", value)
        text = text.replace("{{" + key + "}}", value)
    return text


# Strip the AMD copyright footer that every source page ends with -- the
# merged PDF gets exactly one, at the very end.
FOOTER_RE = re.compile(
    r'<p class="sphinxhide"[^>]*>.*?</p>\s*<p class="sphinxhide"[^>]*>.*?</p>\s*$',
    re.DOTALL,
)

# Drop "## Next steps" / "## Next Steps" / "## 4. Next Steps { #anchor }" /
# "## Where to go next" (and everything after it, up to the next "## " or
# end) -- these are internal site-nav aids that don't make sense in a linear
# PDF (the sibling pages they point to are already merged in as later
# chapters).
NEXT_STEPS_RE = re.compile(
    r'\n##\s*(?:\d+\.\s*)?(?:Next [Ss]teps|Where to [Gg]o [Nn]ext)\b[^\n]*\n.*?(?=\n## |\Z)',
    re.DOTALL,
)

# Replace the "## Downloads" section (and its content, up to the next "## "
# or end) -- download links/tables belong on the live website, not baked
# into a static PDF (they'd also go stale as new versions ship).
DOWNLOADS_SECTION_RE = re.compile(
    r'\n## Downloads\n.*?(?=\n## |\Z)',
    re.DOTALL,
)


def convert_admonition_tabs(text: str) -> str:
    """Flatten mkdocs-material `=== "Label"` tab blocks into headings.

    PDF output has no JS/CSS tab widget, so every tab must render linearly.
    Recursively handles nested tabs (e.g. client tabs containing OS tabs).
    """
    lines = text.split("\n")

    def parse(start: int, indent: int, level: int):
        out = []
        i = start
        n = len(lines)
        while i < n:
            line = lines[i]
            if line.strip() == "":
                out.append("")
                i += 1
                continue
            cur_indent = len(line) - len(line.lstrip(" "))
            if cur_indent < indent:
                break
            content = line[indent:] if cur_indent >= indent else line
            m = re.match(r'^=== "(.+)"\s*$', content)
            if m:
                heading_level = min(6, level)
                out.append("#" * heading_level + " " + m.group(1))
                out.append("")
                nested_out, i2 = parse(i + 1, indent + 4, level + 1)
                out.extend(nested_out)
                i = i2
                continue
            out.append(content)
            i += 1
        return out, i

    out, _ = parse(0, 0, 4)
    return "\n".join(out)


# Links to the site-wide Downloads page (docs/downloads/index.md) don't
# resolve to anything sensible in a standalone PDF -- they'd either render
# as a local filesystem path (e.g. file:///home/you/...), or dangle if the
# merged PDF doesn't happen to carry its own "## Downloads" section. Just
# drop the hyperlink and keep the plain link text -- the live website link
# still works fine since this only touches the copy merged into the PDF.
DOWNLOADS_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((?:\.\./)*downloads/index\.md(?:#[\w-]+)?\)"
)


def fix_cross_links(text: str, slug_map: dict) -> str:
    """Rewrite links between merged sibling pages into in-document anchors."""
    text = DOWNLOADS_LINK_RE.sub(r"\1", text)
    for filename, slug in slug_map.items():
        # file.md#fragment -> #fragment (keep the more specific fragment)
        text = re.sub(
            r"\(" + re.escape(filename) + r"#([\w-]+)\)", r"(#\1)", text
        )
        # bare file.md -> #slug-of-that-chapter
        text = re.sub(
            r"\(" + re.escape(filename) + r"\)", f"(#{slug})", text
        )
    return text


def slugify(heading: str) -> str:
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


# Matches markdown image references, e.g. ![alt text](diagrams/foo.svg).
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def fix_image_paths(text: str, src_dir: Path) -> str:
    """Rewrite image paths so they resolve against the PDF's base_url
    (REPO_ROOT), not the source file's own directory.

    Each source page's image references (e.g. `diagrams/foo.svg`) are
    written relative to that page's own folder, which is correct for the
    live mkdocs site. But the merged PDF is rendered from a single HTML
    string with `base_url=REPO_ROOT`, so an unmodified relative path
    resolves to the wrong location and weasyprint silently drops the
    image. Rewrite each relative (non-http/data/absolute) image path to be
    relative to REPO_ROOT instead.
    """
    rel_dir = src_dir.relative_to(REPO_ROOT)

    def repl(m: "re.Match[str]") -> str:
        alt, src = m.group(1), m.group(2)
        if re.match(r"^(https?://|data:|/)", src):
            return m.group(0)
        return f"![{alt}]({(rel_dir / src).as_posix()})"

    return IMAGE_RE.sub(repl, text)


def strip_self_download_row(text: str, output_name: str) -> str:
    """Drop any table row / list line that links to this PDF's own output
    file. A tab's overview page links to its PDF guide from a Downloads
    section for the live site -- but inside the merged PDF itself that link
    is self-referential (and resolves to a local filesystem path when
    rendered), so it must not appear in the PDF output.
    """
    pattern = re.compile(r"\]\(" + re.escape(output_name) + r"\)")
    lines = [ln for ln in text.split("\n") if not pattern.search(ln)]
    return "\n".join(lines)


def replace_downloads_section(text: str, tab_name: str) -> str:
    """Swap the "## Downloads" section for a short, link-free pointer back
    to the website. Download links/tables (and their version numbers) are
    for the live site only -- a static PDF shouldn't ship hardcoded links
    that can go stale.
    """
    replacement = (
        f"\n## Downloads\n\nDownload the MCP server for your platform from "
        f"the **{tab_name}** tab on the AMD Embedded Agentic AI Suite "
        f"website (Early Access Lounge).\n"
    )
    return DOWNLOADS_SECTION_RE.sub(replacement, text)


def load_section(path: Path, slug_map: dict, output_name: str, tab_name: str,
                  extra: dict | None = None) -> str:
    raw = path.read_text(encoding="utf-8")
    if extra:
        raw = expand_macros(raw, extra)
    raw = FOOTER_RE.sub("", raw)
    raw = NEXT_STEPS_RE.sub("", raw)
    raw = fix_cross_links(raw, slug_map)
    raw = fix_image_paths(raw, path.parent)
    raw = replace_downloads_section(raw, tab_name)
    raw = strip_self_download_row(raw, output_name)
    raw = convert_admonition_tabs(raw)
    return raw.strip() + "\n"


PDF_CSS = """
@page {
    size: Letter;
    margin: 25mm 20mm 20mm 20mm;
    @top-left {
        content: "AMD Embedded Agentic AI Suite";
        font-family: "Segoe UI", Calibri, Arial, Helvetica, sans-serif;
        font-size: 8pt;
        color: #595959;
    }
    @top-right {
        content: string(doc-title);
        font-family: "Segoe UI", Calibri, Arial, Helvetica, sans-serif;
        font-size: 8pt;
        color: #595959;
    }
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: "Segoe UI", Calibri, Arial, Helvetica, sans-serif;
        font-size: 9pt;
        color: #333;
    }
}
@page cover {
    @top-left { content: none; }
    @top-right { content: none; }
    @bottom-center { content: none; }
    counter-reset: page 0;
}
.cover { page: cover; }
body { font-family: "Segoe UI", Calibri, Arial, Helvetica, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1a1a1a; }
h1 { color: #1a1a1a; font-size: 21pt; border-bottom: 1.5pt solid #1a1a1a; padding-bottom: 6px; page-break-before: always; string-set: doc-title content(text); }
h1:first-of-type { page-break-before: avoid; }
h2 { color: #1a1a1a; font-size: 15.5pt; margin-top: 1.6em; }
h3 { color: #1a1a1a; font-size: 12.5pt; margin-top: 1.3em; }
h4, h5 { color: #1a1a1a; }
a { color: #0563C1; text-decoration: none; }
img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
code, pre { font-family: Consolas, "SFMono-Regular", Menlo, monospace; }
pre { background: #f5f5f5; padding: 10px 12px; border-radius: 4px; font-size: 9pt; overflow-wrap: break-word; white-space: pre-wrap; border: 0.75pt solid #e2e2e2; }
pre code { background: none; padding: 0; color: #1a1a1a; }
code { background: #f5f5f5; padding: 1px 4px; border-radius: 3px; font-size: 9.5pt; color: #a83e00; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 9.5pt; }
thead tr { border-top: 1.5pt solid #333; border-bottom: 1.5pt solid #333; }
th { text-align: left; font-weight: 700; padding: 6px 8px; }
td { text-align: left; padding: 6px 8px; border-bottom: 0.75pt solid #ddd; }
tbody tr:last-child td { border-bottom: 1pt solid #333; }
.admonition, details { background: #f2f2f2; border: none; padding: 10px 14px; margin: 1em 0; border-radius: 4px; }
.admonition-title { font-weight: 700; margin-bottom: 4px; display: block; color: #1a1a1a; }
summary { font-weight: 700; cursor: pointer; }
.cover { text-align: center; margin-top: 22%; }
.cover .kicker { text-align: left; font-size: 10pt; color: #595959; border-bottom: 1px solid #ccc; padding-bottom: 8px; margin: 0 0 18% 0; }
.cover h1 { border: none; page-break-before: avoid; font-size: 24pt; margin-bottom: 30px; }
.cover img.logo { width: 150px; margin: 30px auto; display: block; }
.cover .subtitle { color: #444; font-size: 11.5pt; max-width: 80%; margin: 20px auto; }
.cover .date { color: #595959; font-size: 10pt; margin-top: 12px; }
.cover .copyright { margin-top: 60px; font-size: 10pt; color: #333; }
.cover .bottom-rule { border: none; border-top: 2px solid #0563C1; margin-top: 18%; }
.toc { page-break-before: always; }
.toc h2 { margin-top: 0; }
.toc ul { list-style: none; padding-left: 0; }
.toc li { margin: 6px 0; }
.toc a { color: #0563C1; font-weight: 600; }
"""


def build(config_path: str) -> None:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    title = config["title"]
    subtitle = config.get("subtitle", "")
    tab_name = config.get("tab_name", title.split("—")[0].strip())
    kicker = config.get("kicker", "Reference Guide")
    output = REPO_ROOT / config["output"]
    sources = [REPO_ROOT / s for s in config["sources"]]

    macros = load_mkdocs_extra()
    macros.update(config.get("macros", {}))

    # Build filename -> anchor-slug map from each source's first H1.
    slug_map = {}
    for src in sources:
        text = src.read_text(encoding="utf-8")
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        heading = m.group(1).strip() if m else src.stem
        slug_map[src.name] = slugify(heading)

    sections = [load_section(src, slug_map, output.name, tab_name, macros) for src in sources]

    toc_items = []
    for src in sources:
        text = src.read_text(encoding="utf-8")
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        heading = m.group(1).strip() if m else src.stem
        toc_items.append(f'<li><a href="#{slugify(heading)}">{heading}</a></li>')

    body_md = "\n\n".join(sections)
    exts = [
        "tables",
        "fenced_code",
        "admonition",
        "attr_list",
        "toc",
        "md_in_html",
        "pymdownx.superfences",
        "pymdownx.details",
        "pymdownx.highlight",
        "sane_lists",
    ]
    body_html = md.markdown(
        body_md,
        extensions=exts,
        extension_configs={"toc": {"permalink": False}},
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{PDF_CSS}</style>
</head>
<body>
<div class="cover">
<div class="kicker">{kicker}</div>
<h1>{title}</h1>
<img class="logo" src="deploy/pdf/assets/amd-logo.png" alt="AMD">
<p class="subtitle">{subtitle}</p>
<p class="date">{date.today().strftime('%B %d, %Y')}</p>
<p class="copyright">Copyright &copy; 2026 Advanced Micro Devices, Inc.</p>
<hr class="bottom-rule">
</div>
<div class="toc">
<h2>Contents</h2>
<ul>{''.join(toc_items)}</ul>
</div>
{body_html}
<hr>
<p style="text-align:center; font-size:8pt; color:#888;">
Copyright &copy; 2026 Advanced Micro Devices, Inc &middot;
<a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a>
</p>
</body>
</html>
"""

    output.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(REPO_ROOT)).write_pdf(str(output))
    print(f"Wrote {output} ({output.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: build_tab_pdf.py <config.json>", file=sys.stderr)
        sys.exit(1)
    build(sys.argv[1])
