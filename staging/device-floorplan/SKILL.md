---
name: device-floorplan
description: >
  Generate an interactive HTML5 Canvas device floorplan viewer with binary data loading (FPDV format)
  for any AMD/Xilinx FPGA or Versal device. Uses Struct-of-Arrays (SoA) TypedArrays for fast load
  and low memory, plus ImageData pixel-write rendering for ~82× faster zoomed-out frames. Shows all site types with zoom/pan/hover, drag-right-to-zoom-in / drag-left-to-zoom-out
  rubber-band zoom, SLR filter (hierarchical SLR→CR filtering for multi-SLR devices), SLR boundary
  visualization, clock region filtering (multi-select), clock track visualization (disabled by default),
  and focus-highlight mode. Use when user asks to "show device floorplan", "visualize device",
  "create device view", "show device map", "view FPGA layout", or "generate floorplan viewer".
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
| Field | Value |
|-------|-------|
| **Skill Name** | device-floorplan |
| **Description** | Generate an interactive HTML5 Canvas device floorplan viewer with binary SoA data loading and ImageData pixel-write rendering for any AMD/Xilinx FPGA or Versal device. 2.5× smaller data files, ~10× faster load vs JSON (v2), ~82× faster zoomed-out render via direct pixel writes. |
| **Version** | 1.0.0 |
| **Vivado Version** | 2024.2+ |
| **Platform** | vivado-mcp-se |
| **Device Families** | Versal, UltraScale+, UltraScale, 7-Series, Zynq |
| **Estimated Time** | 2-5 minutes |
| **Complexity** | beginner |
| **Author** | Vivado AI Skills Team |

# Device Floorplan Viewer

Generates an interactive HTML5 Canvas floorplan from any Vivado-supported device. Queries all sites via `vivado_execute`, exports to JSON, converts to compact binary (FPDV format), and creates a self-contained viewer with:

- **Binary SoA loading** — TypedArray views over ArrayBuffer; zero-copy decode, ~10× faster than JSON.parse
- **ImageData pixel-write rendering** — at zoomed-out view (baseSize ≤ 1.5px), bypasses Canvas API entirely via `getImageData` → direct RGBA pixel writes → `putImageData`; ~82× faster than `fillRect` for 1.56M sites
- **Zoom/pan/hover** — scroll to zoom, right-drag to pan, hover for site info (lazy name decode)
- **Drag-right to zoom in** — red rubber-band rectangle zooms into the selected area
- **Drag-left to zoom out** — blue rubber-band rectangle zooms out (proportional to rectangle size)
- **SLR filter** — hierarchical All/S0/S1/S2/S3 buttons for multi-SLR (SSIT) devices; automatically filters the CR list
- **SLR boundary visualization** — thick color-coded rectangles with labels for each SLR
- **Clock region multi-select** — filtered by selected SLRs
- **Clock track overlay** — HROUTE, HDISTR, LEAF bands, VROUTE columns (disabled by default, user enables via checkbox)
- **Primitive focus-highlight mode** — double-click legend to isolate a site type

See [REFERENCE.md](REFERENCE.md) for the complete HTML template, binary format spec, converter script, and color assignment rules.

## Performance Benchmarks

Measured on xcvp1902 (Versal Premium, 2×2 SSIT, 1,561,211 sites, 68 types, 264 CRs):

| Metric | JSON | Binary SoA | Improvement |
|--------|-----------|------------------|-------------|
| Data file size | 116 MB | 47.2 MB | **2.5× smaller** |
| Network fetch | 804 ms | 240 ms | **3.3× faster** |
| Parse/decode | ~8-15 s (JSON.parse + object creation) | ~50 ms (TypedArray views) | **~200× faster** |
| JS heap (data) | ~500 MB (1.56M objects + strings) | ~50 MB (typed arrays) | **~10× less** |
| Render loop | Property access per site (`s.x`, `s.y`) | Direct array index (`siteXs[i]`, `siteYs[i]`) | Cache-friendly |
| Zoomed-out render | ~4,293 ms (1.56M `fillRect` calls) | ~53 ms (ImageData pixel writes) | **~82× faster** |

## Tools Used

| Tool | Purpose |
|------|---------|
| `vivado_start` | Start Vivado in TCL mode |
| `vivado_execute` | Run Tcl commands: `link_design`, `get_sites`, `get_property` |
| `vivado_stop` | Stop Vivado session when done |
| Agent file tools | Write JSON data, converter script, and HTML viewer files |
| Terminal | Run Python converter + start HTTP server |

## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call.
- **Batch Tcl commands** with semicolons to reduce round-trips.
- **NEVER** use per-site `get_property` loops. Always batch: `get_property RPM_X [get_sites -filter ...]` returns all values in one call.
- **Write the HTML file using the agent file tools** — do NOT write it via Vivado Tcl.
- The HTML viewer loads site data from `.bin` via `fetch()` as ArrayBuffer — it MUST be served over HTTP, not `file://`.
- If a previous HTTP server is already running on the target port, reuse it.
- Use `vivado_todos` to track progress for this multi-step skill.

## Rendering Performance

Large devices (1M+ sites) require these optimizations (already built into the REFERENCE.md template):

| Optimization | What it does | Impact |
|---|---|---|
| **Binary SoA loading** | TypedArray views over raw ArrayBuffer; no JSON.parse, no object allocation | ~200× faster parse; ~10× less memory |
| **Lazy name decode** | Site names decoded from UTF-8 only on hover via `getSiteName(idx)` | Avoids creating 1.56M strings at load |
| **requestAnimationFrame debounce** | Coalesces multiple `render()` calls into one per display frame during drag/zoom | Eliminates redundant repaints (~50% during interaction) |
| **ImageData pixel-write** | When `use1px && noFilter && !focusedType`, bypasses Canvas API entirely: `getImageData` → direct RGBA pixel writes → `putImageData`. Precomputed `_typeRGBA` color table avoids hex parsing | **~82× faster** zoomed-out render (53ms vs 4,293ms for 1.56M sites) |
| **1px integer fast-path** (fallback) | When `baseSize ≤ 1.5` but filter/focus active, uses `fillRect(sx\|0, sy\|0, 1, 1)` — avoids sub-pixel anti-aliasing | Faster than shaped drawing at low zoom |
| **Per-type viewport culling** | Precomputes `typeBounds[type]` (minX/maxX/minY/maxY) at init; skips entire type if bounding box is outside viewport | Saves iterating 100K+ sites per offscreen type when zoomed in |
| **CR boundaries off by default** | `showCRBounds = false` — users enable via checkbox when analyzing specific regions | Saves drawing ~200 dashed rectangles + text labels per frame |
| **Clock tracks off by default** | `showClkTracks = false` — users enable via checkbox | Saves drawing thousands of horizontal/vertical track lines |
| **willReadFrequently** | Canvas created with `getContext('2d', { willReadFrequently: true })` — optimizes for repeated `getImageData` calls during zoom/pan | Eliminates Chrome readback warning; faster `getImageData` |
| **Fast-alpha path** | When no SLR/CR filter and no focus-highlight, sets `fillStyle`/`globalAlpha` once per type instead of per site | Reduces canvas state changes by ~1M per frame |

## FPDV Binary Format

All values are little-endian:

```
Header (16 bytes):
  char[4]  magic = "FPDV"
  uint32   version = 1
  uint32   siteCount
  uint16   typeCount
  uint16   crCount

Type name table:
  [uint8 nameLen, char[nameLen]] × typeCount
  Padded to 4-byte boundary

CR name table:
  [uint8 nameLen, char[nameLen]] × crCount
  Padded to 4-byte boundary

Site data (SoA layout):
  uint8[siteCount]         typeIds    — type index per site (padded to 4)
  uint16[siteCount]        crIds      — CR index per site (padded to 4)
  int32[siteCount]         xs         — RPM_X per site
  int32[siteCount]         ys         — RPM_Y per site
  uint32[siteCount + 1]    nameOffsets — byte offset into nameData
  uint8[variable]          nameData   — concatenated UTF-8 site names
```

## Mandatory Workflow

**⚠️ Execute steps SEQUENTIALLY. Wait for each `vivado_execute` to complete before the next.**

```
Device Floorplan Progress:
- [ ] Step 1: Determine device part
- [ ] Step 2: Start Vivado, link device
- [ ] Step 3: Export site data to JSON
- [ ] Step 4: Convert JSON to binary (FPDV)
- [ ] Step 5: Export clock track data
- [ ] Step 6: Generate HTML viewer
- [ ] Step 7: Serve and open in browser
- [ ] Step 8: Stop Vivado
```

### Step 1: Determine Device Part

If the user did not provide a device part, ask for one. Accept any valid AMD/Xilinx part string.

Derive a short device name for file naming:
```
Part: xcvm1102-sfva784-2MP-e-S  →  device_name: xcvm1102
Part: xcvu9p-flga2104-2L-e      →  device_name: xcvu9p
Part: xc7a35tcpg236-1           →  device_name: xc7a35t
```

Rule: take the part string up to the first `-`, stripping any speed grade suffix.

### Step 2: Start Vivado and Link Device

Start Vivado in TCL mode (default — do NOT use `gui_mode=true`):
```
vivado_start(working_dir=<output_directory>)
```

Link the device (no project needed):
```tcl
link_design -part <FULL_PART_STRING>
```

### Step 3: Export Site Data to JSON

Run this single `vivado_execute` call to export ALL sites with RPM coordinates and clock regions:

```tcl
set all [get_sites -quiet]; set types [lsort -unique [get_property SITE_TYPE $all]]; set fp [open "<device_name>_sites.json" w]; puts $fp "\["; set first 1; foreach st $types { set ss [get_sites -quiet -filter "SITE_TYPE == $st"]; if {[llength $ss] == 0} continue; set names [get_property NAME $ss]; set rpx [get_property RPM_X $ss]; set rpy [get_property RPM_Y $ss]; set crs [get_property CLOCK_REGION $ss]; foreach n $names x $rpx y $rpy c $crs { if {!$first} {puts $fp ","} else {set first 0}; puts $fp [format {{"t":"%s","n":"%s","x":%s,"y":%s,"cr":"%s"}} $st $n $x $y $c] } }; puts $fp "\]"; close $fp; puts "Exported [llength $all] sites of [llength $types] types"
```

**Validation:** Verify RPM_X/Y are populated (not all empty/zero). Quick check:
```tcl
get_property RPM_X [lindex [get_sites -filter {SITE_TYPE == SLICEL || SITE_TYPE == SLICE}] 0]
```
If empty, fall back to tile grid coordinates — see REFERENCE.md § Fallback Coordinates.

### Step 4: Convert JSON to Binary (FPDV)

Write the `json_to_bin.py` converter script to the output directory (see REFERENCE.md § Converter Script for the complete source), then run it:

```powershell
python json_to_bin.py <device_name>_sites.json
```

This produces `<device_name>_sites.bin` — typically 2.5× smaller than the JSON. Conversion takes ~3-5 seconds for 1.5M+ sites.

### Step 5: Export Clock Track Data

**5a. BUFDIV_LEAF sites** — these define the RCLK distribution rows:

```tcl
set bdl [get_sites -quiet -filter {SITE_TYPE == BUFDIV_LEAF}]; if {[llength $bdl] > 0} { set fp [open "<device_name>_bufdiv_leaf.csv" w]; puts $fp "SITE_NAME,RPM_X,RPM_Y,CLOCK_REGION"; set names [get_property NAME $bdl]; set rpx [get_property RPM_X $bdl]; set rpy [get_property RPM_Y $bdl]; set crs [get_property CLOCK_REGION $bdl]; foreach n $names x $rpx y $rpy c $crs { puts $fp "$n,$x,$y,$c" }; close $fp; puts "Exported [llength $bdl] BUFDIV_LEAF sites" } else { puts "No BUFDIV_LEAF sites — skip clock leaf tracks" }
```

**5b. Clock buffer column positions:**

```tcl
foreach buftype {BUFGCE BUFG_FABRIC BUFG_GT BUFGCTRL BUFG BUFH BUFR} { set bs [get_sites -quiet -filter "SITE_TYPE == $buftype"]; if {[llength $bs] > 0} { set xs [lsort -unique -real [get_property RPM_X $bs]]; set ys [lsort -unique -real [get_property RPM_Y $bs]]; puts "$buftype count=[llength $bs] X_unique=$xs Y_range=[lindex $ys 0]-[lindex $ys end]" } }
```

**If BUFDIV_LEAF does not exist** (e.g. 7-Series): Set `CLK_TRACK_DATA = null` in the HTML — clock track overlay will be disabled.

### Step 6: Generate HTML Viewer

Create `<device_name>_device_view.html` using the template from [REFERENCE.md](REFERENCE.md) § HTML Template.

**Substitutions required in the template:**

| Placeholder | Source | Example |
|-------------|--------|---------|
| `{{DEVICE_NAME}}` | Step 1 | `xcvm1102` |
| `{{PART}}` | User input | `xcvm1102-sfva784-2MP-e-S` |
| `{{DATA_FILE}}` | Step 4 output | `xcvm1102_sites.bin` |
| `{{TYPE_CONFIG}}` | Build from site types found | See REFERENCE.md § Color Assignment |
| `{{CLK_TRACK_DATA}}` | Build from Step 5 data | See REFERENCE.md § Clock Track Data |
| `{{DRAW_ORDER}}` | Array of all type names | Logic first, special last |

### Overlay Placeholders (for consuming skills)

These placeholders are set to `null` by default when device-floorplan runs standalone. Consuming skills (e.g., congestion-analysis, dfx-floorplan-review, clock-placer-analysis) populate them to add domain-specific visual overlays on top of the base floorplan.

| Placeholder | Type | Purpose | Default |
|-------------|------|---------|---------|
| `{{OVERLAY_CR_FILLS}}` | `Object` | Color clock region backgrounds: `{ "X0Y2": { fill: "rgba(R,G,B,A)", label: "text", labelColor: "#fff" } }` | `null` |
| `{{OVERLAY_RECTS}}` | `Array` | Draw rectangles at device coordinates: `[{ x1, y1, x2, y2, color, dash, lineWidth, fill, label }]` | `null` |
| `{{OVERLAY_SITE_HIGHLIGHTS}}` | `Array` | Highlight sites by name glob: `[{ pattern: "RAMB36_X0Y*", color: "#ff0", label: "Failing" }]` | `null` |
| `{{OVERLAY_LEGEND}}` | `Array` | Extra legend entries: `[{ color: "#f87171", label: "BRAM ≥95%", shape: "rect\|dash\|circle" }]` | `null` |
| `{{OVERLAY_TITLE}}` | `string` | Title shown in overlay panel: `"Congestion Hotspot Map"` | `null` |

**Overlay rendering order:**
1. CR fills — drawn before sites (semi-transparent backgrounds)
2. Sites — normal rendering
3. Rectangles — drawn after sites (borders/outlines on top)
4. Site highlights — drawn after sites (glowing dots for specific sites)

**Example — congestion analysis overlay:**
```javascript
// OVERLAY_CR_FILLS: color CRs by BRAM utilization
{ "X0Y2": { fill: "rgba(248,113,113,0.3)", label: "BRAM 100%", labelColor: "#f87171" },
  "X1Y2": { fill: "rgba(251,191,36,0.2)", label: "BRAM 85%", labelColor: "#fbbf24" } }

// OVERLAY_RECTS: draw congestion window boundaries
[{ x1: 525, y1: 11840, x2: 1095, y2: 19200, color: "#f87171", dash: true, label: "East Short L5 (89%)" }]

// OVERLAY_LEGEND
[{ color: "rgba(248,113,113,0.3)", label: "BRAM ≥95%", shape: "rect" },
 { color: "#f87171", label: "Congestion Window", shape: "dash" }]

// OVERLAY_TITLE
"Congestion Hotspot Map"
```

**TYPE_CONFIG construction:** For each unique site type found in the device, assign a color, category, and shape using the rules in REFERENCE.md § Color Assignment Rules. Types not matching any pattern get category "Other", color gray, shape rect.

**CLK_TRACK_DATA construction:** From the BUFDIV_LEAF CSV, group by CLOCK_REGION to get per-CR bands (minX, maxX, minY, maxY, cols=unique X count, rows=unique Y count). From the sites JSON (already loaded), extract unique X positions for BUFGCE, BUFG_FABRIC, BUFG_GT and Y positions for BUFG_FABRIC. For BUFG_FABRIC Ys, simplify to band-start positions only (first Y in each group where gaps > 100). Format as the JavaScript object shown in REFERENCE.md § Clock Track Data Format.

**⚠️ IMPORTANT:** Always embed the built `CLK_TRACK_DATA` object in the HTML (not `null`). The clock track checkbox is unchecked by default — users enable it when needed. Only set `CLK_TRACK_DATA = null` if the device has NO BUFDIV_LEAF sites (e.g. 7-Series).

**SLR detection:** Multi-SLR devices have clock region names prefixed with `S0`, `S1`, `S2`, `S3` (e.g. `S0X0Y2`, `S1X3Y4`). The viewer automatically detects SLR prefixes, computes SLR bounding boxes, and shows the SLR filter. For single-SLR devices (CRs like `X0Y2` without SLR prefix), the SLR filter is hidden automatically.

### Step 7: Serve and Open in Browser

Start a Python HTTP server in the output directory:

```powershell
cd <output_directory>
python -m http.server 8099
```

Use async mode for the terminal. If port 8099 is busy, try 8100, 8101, etc.

Open the browser to `http://localhost:<port>/<device_name>_device_view.html`.

### Step 8: Stop Vivado

```
vivado_stop(session_id=<session_id>)
```

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `link_design` fails | Invalid part string | Verify part with `vivado_doc_search` or `get_parts -filter` |
| RPM_X/Y all zero | Device family doesn't populate RPM | Use tile GRID_POINT_X/Y fallback (see REFERENCE.md) |
| Binary fetch fails in browser | Serving via `file://` | Must use HTTP server (`python -m http.server`) |
| `json_to_bin.py` fails | Missing JSON or wrong format | Verify JSON has `t`, `n`, `x`, `y`, `cr` fields |
| Device renders as thin strip | Y-flip error in `resetView()` | Ensure `offsetY = ch/2 + cy*scale` (positive sign for flip) |
| Hover is slow on large devices | Linear search | Spatial grid (`GRID_SIZE=100`) provides O(1) lookup |
| No BUFDIV_LEAF sites | 7-Series or simplified device | Set `CLK_TRACK_DATA = null`, clock track UI hidden |
| Port already in use | Previous server still running | Try next port (8100, 8101) or reuse existing server |
| Too many site types (>40) | Large device with many primitives | Color assignment auto-extends palette — no issue |
| TypedArray alignment error | Binary file corrupted | Re-run `json_to_bin.py`; verify padding to 4-byte boundaries |

## Examples

**"Show me the floorplan of xcvp1902"** → Steps 1-8 → Interactive viewer with 1.56M sites, 68 types, 264 clock regions, binary loaded in ~300ms.
