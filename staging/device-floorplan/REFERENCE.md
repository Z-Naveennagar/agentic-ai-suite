<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Device Floorplan — Reference

## Site JSON Schema

Each site is a JSON object with these fields:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `t` | string | Site type | `"SLICEL"` |
| `n` | string | Site name | `"SLICE_X0Y231"` |
| `x` | number | RPM_X coordinate | `570` |
| `y` | number | RPM_Y coordinate | `19200` |
| `cr` | string | Clock region | `"X0Y3"` |

File format: JSON array of site objects.
```json
[
  {"t":"SLICEL","n":"SLICE_X0Y231","x":570,"y":19200,"cr":"X0Y3"},
  {"t":"RAMB36","n":"RAMB36_X0Y10","x":525,"y":8320,"cr":"X0Y2"}
]
```

## FPDV Binary Format

The FPDV (FPga Device View) binary format stores site data in a compact, zero-copy-friendly layout using Struct-of-Arrays (SoA).

```
Header (16 bytes):
  Offset 0:  char[4]   magic = "FPDV"
  Offset 4:  uint32    version = 1
  Offset 8:  uint32    siteCount
  Offset 12: uint16    typeCount
  Offset 14: uint16    crCount

Type name table (variable length):
  Repeated typeCount times: [uint8 nameLen, char[nameLen]]
  Padded to 4-byte boundary after all entries

CR name table (variable length):
  Repeated crCount times: [uint8 nameLen, char[nameLen]]
  Padded to 4-byte boundary after all entries

Site arrays (SoA — Struct of Arrays):
  typeIds:     uint8[siteCount]         — padded to 4-byte boundary
  crIds:       uint16[siteCount]        — padded to 4-byte boundary
  xs:          int32[siteCount]         — RPM_X values
  ys:          int32[siteCount]         — RPM_Y values
  nameOffsets: uint32[siteCount + 1]    — byte offsets into nameData
  nameData:    uint8[variable]          — concatenated UTF-8 site names
```

All multi-byte values are little-endian. The SoA layout enables zero-copy TypedArray views directly from the ArrayBuffer.

## Converter Script (json_to_bin.py)

```python
#!/usr/bin/env python3
"""Convert device sites JSON to FPDV binary format.

Usage: python json_to_bin.py <input.json> [output.bin]
If output is omitted, replaces .json with .bin in the input filename.
"""
import json, struct, array, sys, os, time

def convert(input_path, output_path=None):
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + '.bin'
    
    t0 = time.time()
    with open(input_path, 'r', encoding='utf-8') as f:
        sites = json.load(f)
    
    n = len(sites)
    # Build type and CR lookup tables
    type_set = sorted(set(s['t'] for s in sites))
    cr_set = sorted(set(s['cr'] for s in sites))
    type_map = {t: i for i, t in enumerate(type_set)}
    cr_map = {c: i for i, c in enumerate(cr_set)}
    
    assert len(type_set) <= 255, f"Too many types: {len(type_set)}"
    assert len(cr_set) <= 65535, f"Too many CRs: {len(cr_set)}"
    
    # Header
    header = struct.pack('<4sIIHH', b'FPDV', 1, n, len(type_set), len(cr_set))
    
    # Name tables
    def pack_names(names):
        parts = []
        for name in names:
            b = name.encode('utf-8')
            parts.append(struct.pack('B', len(b)))
            parts.append(b)
        data = b''.join(parts)
        pad = (4 - len(data) % 4) % 4
        return data + b'\x00' * pad
    
    type_table = pack_names(type_set)
    cr_table = pack_names(cr_set)
    
    # Site arrays
    type_ids = array.array('B', (type_map[s['t']] for s in sites))
    cr_ids = array.array('H', (cr_map[s['cr']] for s in sites))
    xs = array.array('i', (int(s['x']) for s in sites))
    ys = array.array('i', (int(s['y']) for s in sites))
    
    # Names with offset table
    name_parts = []
    offsets = array.array('I')
    off = 0
    for s in sites:
        offsets.append(off)
        b = s['n'].encode('utf-8')
        name_parts.append(b)
        off += len(b)
    offsets.append(off)
    name_data = b''.join(name_parts)
    
    def pad4(data):
        p = (4 - len(data) % 4) % 4
        return data + b'\x00' * p if p else data
    
    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(type_table)
        f.write(cr_table)
        f.write(pad4(type_ids.tobytes()))
        f.write(pad4(cr_ids.tobytes()))
        f.write(xs.tobytes())
        f.write(ys.tobytes())
        f.write(offsets.tobytes())
        f.write(name_data)
    
    elapsed = time.time() - t0
    out_size = os.path.getsize(output_path)
    in_size = os.path.getsize(input_path)
    print(f"Converted {n:,} sites in {elapsed:.1f}s")
    print(f"  Input:  {in_size:,} bytes ({in_size/1024/1024:.1f} MB)")
    print(f"  Output: {out_size:,} bytes ({out_size/1024/1024:.1f} MB)")
    print(f"  Ratio:  {out_size/in_size*100:.1f}%")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python json_to_bin.py <input.json> [output.bin]")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
```

## Color Assignment Rules

Assign colors and shapes based on site type name patterns. Process rules top-to-bottom; first match wins.

| Pattern | Category | Colors (cycle through) | Shape |
|---------|----------|----------------------|-------|
| `SLICEL` | Logic | `#4fc3f7` | rect |
| `SLICEM` | Logic | `#29b6f6` | rect |
| `CLB*` | Logic | `#4fc3f7` | rect |
| `RAMB36*` | Memory | `#66bb6a` | rect |
| `RAMB18*` with `_L` | Memory | `#43a047` | rect |
| `RAMB18*` with `_U` | Memory | `#388e3c` | rect |
| `RAMB*` (other) | Memory | `#66bb6a` | rect |
| `FIFO*` | Memory | `#2e7d32` | rect |
| `URAM*` | Memory | `#00c853` | tall |
| `DSP48*` | DSP | `#ffa726` | rect |
| `DSP58*` with `CPLX` | DSP | `#ff9800` | rect |
| `DSP58*` (other) | DSP | `#ffa726` | rect |
| `BUFGCE` | Clocking | `#ab47bc` | diamond |
| `BUFG_GT` | Clocking | `#9c27b0` | diamond |
| `BUFG_FABRIC` | Clocking | `#7b1fa2` | diamond |
| `BUFGCTRL` | Clocking | `#ab47bc` | diamond |
| `BUFG` (7-Series) | Clocking | `#ab47bc` | diamond |
| `BUFH*` | Clocking | `#9c27b0` | diamond |
| `BUFR*` | Clocking | `#7b1fa2` | diamond |
| `MMCM*` | Clocking | `#e040fb` | diamond |
| `PLL*`, `DPLL*`, `XPLL*` | Clocking | `#d500f9`, `#ba68c8` | diamond |
| `GT*P_QUAD`, `GT*_QUAD` | GT / Serial | `#ef5350` | tall |
| `GT*_COMMON` | GT / Serial | `#e53935` | tall |
| `GT*_CHANNEL` | GT / Serial | `#c62828` | tall |
| `PCIE*` | GT / Serial | `#f44336` | tall |
| `MRMAC*` | GT / Serial | `#e53935` | tall |
| `ILKN*` | GT / Serial | `#d32f2f` | tall |
| `CMAC*` | GT / Serial | `#c62828` | tall |
| `HDIOB*` | I/O | `#ffee58` | rect |
| `XPIOB*` | I/O | `#fdd835` | rect |
| `HPIOB*` | I/O | `#ffee58` | rect |
| `IOB*` | I/O | `#fdd835` | rect |
| `XPHY*` | I/O | `#f9a825` | rect |
| `BITSLICE*` | I/O | `#f9a825` | rect |
| `HPIO*` | I/O | `#fbc02d` | rect |
| `NOC_NMU*` | NoC | `#26c6da`, `#00bcd4` | circle |
| `NOC_NSU*` | NoC | `#00acc1`, `#0097a7` | circle |
| `NOC_NPS*` | NoC | `#00838f`, `#006064` | circle |
| `NPI_*` | NoC | `#004d40` | circle |
| `PS*` (PS7, PS8, PS9) | Processing | `#ff6e40` | tall |
| `DDRMC*` | DDR | `#8d6e63` | tall |
| `HARD_SYNC*` | Other | `#78909c` | rect |
| *anything else* | Other | `#9e9e9e` | rect |

**Shape definitions:**
- `rect`: Square `fillRect(x-sz/2, y-sz/2, sz, sz)`
- `circle`: Circle `arc(x, y, sz*0.6, 0, 2π)`
- `diamond`: Rotated square via `moveTo/lineTo`
- `tall`: Tall rectangle `fillRect(x-sz*0.5, y-sz, sz, sz*2)`

## Clock Track Data Format

The `CLK_TRACK_DATA` JavaScript object (set to `null` if device has no BUFDIV_LEAF):

```javascript
const CLK_TRACK_DATA = {
  // BUFDIV_LEAF bands per clock region
  bufdivLeaf: [
    // One entry per CR that has BUFDIV_LEAF sites
    { cr: 'X0Y2', minX: 525, maxX: 1095, minY: 11840, maxY: 11903, cols: 10, rows: 64 },
    // ... more CRs
  ],
  // Unique X positions of all BUFDIV_LEAF sites across the device
  leafColumnXs: [525, 570, 630, /* ... all unique RPM_X values */],
  // BUFGCE column X positions (vertical routing spines)
  bufgceXs: [2, 497, 1127, 2042],
  bufgceY: 192,  // lowest BUFGCE Y position
  // BUFG_FABRIC column X positions
  bufgFabricXs: [1967, 1968],
  bufgFabricYs: [4160, 11840, 15744],  // Y positions where BUFG_FABRIC exists
  // BUFG_GT
  bufgGtX: 466,
  bufgGtYs: [11840, 15744],
  // Tracks per clock region (Versal/UltraScale = 24)
  tracksPerCR: 24,
};
```

**Building from exported data:**

1. Parse `<device>_bufdiv_leaf.csv`, group by CLOCK_REGION
2. Per CR: compute minX, maxX, minY, maxY, count unique X (cols), count unique Y (rows)
3. Collect all unique RPM_X values across all BUFDIV_LEAF for `leafColumnXs`
4. From clock buffer query output, extract unique X and Y positions

## Fallback Coordinates

If `RPM_X`/`RPM_Y` are empty for all sites (some device configurations), use tile-based coordinates:

```tcl
# Get tile coordinates instead
set all [get_sites -quiet]
set tiles [get_tiles -quiet -of_objects $all]
# For each site, get its tile's grid position
set tile_xs [get_property GRID_POINT_X $tiles]
set tile_ys [get_property GRID_POINT_Y $tiles]
```

Use `GRID_POINT_X` and `GRID_POINT_Y` as the `x` and `y` fields in the JSON. The viewer works with any coordinate system.

## HTML Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Device View — {{DEVICE_NAME}}</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', system-ui, sans-serif; overflow: hidden; height: 100vh; display: flex; }

#sidebar {
  width: 280px; min-width: 280px; background: #16213e; padding: 12px; overflow-y: auto;
  border-right: 1px solid #0f3460; display: flex; flex-direction: column; gap: 8px;
}
#sidebar h2 { font-size: 14px; color: #e94560; margin-bottom: 4px; }
#sidebar h3 { font-size: 12px; color: #8899aa; margin: 8px 0 4px; text-transform: uppercase; letter-spacing: 1px; }

.legend-item {
  display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 4px;
  cursor: pointer; font-size: 12px; user-select: none; transition: background 0.15s;
}
.legend-item:hover { background: #1a3a5c; }
.legend-item.disabled { opacity: 0.3; }
.legend-item.focused { background: #1a3a5c; box-shadow: inset 0 0 0 1.5px currentColor; }
.legend-item.focused .legend-label { font-weight: bold; }
.legend-swatch { width: 14px; height: 14px; border-radius: 2px; flex-shrink: 0; }
.legend-label { flex: 1; }
.legend-count { color: #667; font-size: 11px; }

#controls { display: flex; flex-direction: column; gap: 6px; margin-top: auto; padding-top: 12px; border-top: 1px solid #0f3460; }
#controls button {
  padding: 6px 10px; background: #0f3460; color: #e0e0e0; border: none; border-radius: 4px;
  cursor: pointer; font-size: 12px; transition: background 0.15s;
}
#controls button:hover { background: #e94560; }

#main { flex: 1; position: relative; }
canvas { display: block; width: 100%; height: 100%; }

#tooltip {
  position: absolute; pointer-events: none; background: rgba(22,33,62,0.95); color: #e0e0e0;
  padding: 6px 10px; border-radius: 4px; font-size: 12px; border: 1px solid #0f3460;
  display: none; z-index: 100; white-space: nowrap;
}

#info-bar {
  position: absolute; bottom: 0; left: 0; right: 0; height: 28px; background: rgba(22,33,62,0.9);
  display: flex; align-items: center; padding: 0 12px; font-size: 11px; color: #667;
  border-top: 1px solid #0f3460; gap: 20px;
}

#search-box {
  width: 100%; padding: 5px 8px; background: #0d1b30; color: #e0e0e0; border: 1px solid #0f3460;
  border-radius: 4px; font-size: 12px; outline: none;
}
#search-box:focus { border-color: #e94560; }
#search-box::placeholder { color: #445; }

.category-header {
  display: flex; align-items: center; justify-content: space-between; cursor: pointer;
  padding: 2px 0;
}
.category-header:hover h3 { color: #aabbcc; }
.toggle-all { font-size: 10px; color: #556; cursor: pointer; }
.toggle-all:hover { color: #e94560; }

#slr-filter { margin: 4px 0; }
#slr-filter label { font-size: 11px; color: #8899aa; text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 4px; }
#slr-options { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; }
.slr-btn {
  padding: 3px 10px; background: #0f3460; color: #aab; border: 2px solid #1a4a7a; border-radius: 4px;
  cursor: pointer; font-size: 11px; font-family: monospace; font-weight: bold; transition: all 0.15s;
}
.slr-btn:hover { background: #1a4a7a; color: #fff; }
.slr-btn.active { color: #fff; }

#cr-filter { margin: 4px 0; }
#cr-filter label { font-size: 11px; color: #8899aa; text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 4px; }
#cr-options { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; }
.cr-btn {
  padding: 2px 6px; background: #0f3460; color: #aab; border: 1px solid #1a4a7a; border-radius: 3px;
  cursor: pointer; font-size: 10px; font-family: monospace; transition: all 0.15s;
}
.cr-btn:hover { background: #1a4a7a; color: #fff; }
.cr-btn.active { background: #e94560; color: #fff; border-color: #e94560; }
#cr-show-bounds { margin-top: 4px; display: flex; align-items: center; gap: 6px; font-size: 11px; cursor: pointer; }
#cr-show-bounds input { cursor: pointer; }

#clk-track-controls { margin-top: 2px; }
#clk-track-controls label { display: flex; align-items: center; gap: 6px; font-size: 11px; cursor: pointer; margin-top: 3px; }
#clk-track-controls input { cursor: pointer; }
.clk-track-legend { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; font-size: 10px; }
.clk-track-btn { display: flex; align-items: center; gap: 3px; padding: 2px 6px; background: #0f3460; border: 1px solid #1a4a7a; border-radius: 3px; cursor: pointer; transition: all 0.15s; }
.clk-track-btn:hover { background: #1a4a7a; }
.clk-track-btn.active { border-color: currentColor; }
.clk-track-btn.disabled { opacity: 0.35; }
.clk-track-btn .swatch { width: 14px; height: 3px; border-radius: 1px; }
</style>
</head>
<body>

<div id="sidebar">
  <h2>{{DEVICE_NAME}} Device View (Binary)</h2>
  <input type="text" id="search-box" placeholder="Search site name...">
  <div id="slr-filter">
    <label>SLR</label>
    <div id="slr-options"></div>
  </div>
  <div id="cr-filter">
    <label>Clock Region</label>
    <div id="cr-options"></div>
    <label id="cr-show-bounds"><input type="checkbox" id="cb-show-cr"> Show boundaries</label>
    <div id="clk-track-controls">
      <label><input type="checkbox" id="cb-show-clk-tracks"> Show clock tracks</label>
      <div class="clk-track-legend" id="clk-track-legend" style="display:none"></div>
    </div>
  </div>
  <div id="legend"></div>
  <div id="overlay-panel" style="border-top: 1px solid #0f3460; padding-top: 8px; margin-top: 8px;"></div>
  <div id="controls">
    <button id="btn-reset">Reset View</button>
    <button id="btn-toggle-all">Toggle All</button>
    <button id="btn-screenshot">Save Screenshot</button>
  </div>
</div>

<div id="main">
  <canvas id="canvas"></canvas>
  <div id="tooltip"></div>
  <div id="info-bar">
    <span id="info-zoom">Zoom: 1.0x</span>
    <span id="info-pos">X: 0, Y: 0</span>
    <span id="info-sites">Sites: 0</span>
    <span>Scroll to zoom · Drag-right to zoom in · Drag-left to zoom out · Right-drag to pan · Hover for info · Dbl-click legend to focus</span>
  </div>
</div>

<script>
// ===== TYPE_CONFIG: site type → color/category/shape =====
const TYPE_CONFIG = {{TYPE_CONFIG}};

// ===== SoA state variables =====
let siteCount = 0;
let siteTypes;       // Uint8Array - type index per site
let siteCRs;         // Uint16Array - CR index per site
let siteXs;          // Int32Array - RPM_X per site
let siteYs;          // Int32Array - RPM_Y per site
let _nameOffsets;    // Uint32Array[siteCount+1]
let _nameData;       // Uint8Array
let _decoder = new TextDecoder();
let _nameIndex = null; // lazy: name → index for search
let typeNames = [];  // type index → name string
let crNames = [];    // CR index → name string
let typeSiteIndices = {}; // typeName → Uint32Array of site indices

let visible = {};
let allVisible = true;
let searchHighlightIdx = -1;
let selectedSLRs = new Set();
let selectedCRs = new Set();
let showCRBounds = false;
let showClkTracks = false;
const clkTrackVisible = { hroute: true, hdistr: true, leaf: true, vroute: true };
let focusedType = null;
let clockRegions = {};
let typeBounds = {};
let _rafPending = false;
let slrBounds = {};
const _typeRGBA = {}; // precomputed {typeName: [r, g, b]} for ImageData pixel writes
function _parseHexColor(hex) {
  return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
}

// ===== OVERLAY DATA — populated by consuming skills =====
// CR background fills: { "X0Y2": { fill: "rgba(248,113,113,0.3)", label: "BRAM 100%" }, ... }
const OVERLAY_CR_FILLS = {{OVERLAY_CR_FILLS}};
// Rectangles at device coordinates: [{ x1, y1, x2, y2, color, dash, lineWidth, fill, label }, ...]
const OVERLAY_RECTS = {{OVERLAY_RECTS}};
// Site highlights by name pattern: [{ pattern: "RAMB36_X0Y*", color: "#ff0", label: "Failing" }, ...]
const OVERLAY_SITE_HIGHLIGHTS = {{OVERLAY_SITE_HIGHLIGHTS}};
// Extra legend entries for overlays: [{ color: "#f87171", label: "BRAM ≥95%", shape: "rect|dash|circle" }, ...]
const OVERLAY_LEGEND = {{OVERLAY_LEGEND}};
// Overlay title shown in sidebar: "Congestion Hotspot Map" or null
const OVERLAY_TITLE = {{OVERLAY_TITLE}};
// Precomputed highlight site indices (built at init from patterns)
let _highlightSets = [];

// ===== CLOCK TRACK DATA =====
const CLK_TRACK_DATA = {{CLK_TRACK_DATA}};

// Canvas state
let canvas, ctx;
let offsetX = 0, offsetY = 0, scale = 1;
let isDragging = false, dragStartX, dragStartY, dragOffsetX, dragOffsetY;
let isSelecting = false, selStartX, selStartY, selCurX, selCurY;
let deviceMinX, deviceMaxX, deviceMinY, deviceMaxY;
let hoveredIdx = -1;

// Spatial grid for fast hover lookup
const GRID_SIZE = 100;
let spatialGrid = {};
function gridKey(x, y) { return `${Math.floor(x / GRID_SIZE)},${Math.floor(y / GRID_SIZE)}`; }

function getSiteName(idx) {
  const start = _nameOffsets[idx];
  const end = _nameOffsets[idx + 1];
  return _decoder.decode(_nameData.subarray(start, end));
}

function buildSpatialGrid() {
  spatialGrid = {};
  for (let i = 0; i < siteCount; i++) {
    const k = gridKey(siteXs[i], siteYs[i]);
    if (!spatialGrid[k]) spatialGrid[k] = [];
    spatialGrid[k].push(i);
  }
}

function findNearest(devX, devY, threshold) {
  const gx = Math.floor(devX / GRID_SIZE), gy = Math.floor(devY / GRID_SIZE);
  let nearest = -1, nearestDist = threshold;
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      const cell = spatialGrid[`${gx+dx},${gy+dy}`];
      if (!cell) continue;
      for (const i of cell) {
        if (!visible[typeNames[siteTypes[i]]]) continue;
        const d = Math.abs(siteXs[i] - devX) + Math.abs(siteYs[i] - devY);
        if (d < nearestDist) { nearestDist = d; nearest = i; }
      }
    }
  }
  return nearest;
}

async function loadBinaryData() {
  const loadStart = performance.now();
  try {
    console.time('fetch');
    const resp = await fetch('{{DATA_FILE}}');
    const buf = await resp.arrayBuffer();
    console.timeEnd('fetch');
    const fetchMs = performance.now() - loadStart;

    console.time('decode');
    const dv = new DataView(buf);
    let off = 0;

    // Header (16 bytes)
    const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
    if (magic !== 'FPDV') throw new Error('Invalid binary magic: ' + magic);
    const version = dv.getUint32(4, true);
    siteCount = dv.getUint32(8, true);
    const typeCount = dv.getUint16(12, true);
    const crCount = dv.getUint16(14, true);
    off = 16;

    // Type names
    typeNames = [];
    for (let i = 0; i < typeCount; i++) {
      const len = dv.getUint8(off); off++;
      const bytes = new Uint8Array(buf, off, len);
      typeNames.push(_decoder.decode(bytes));
      off += len;
    }
    // Pad to 4-byte boundary
    off = (off + 3) & ~3;

    // CR names
    crNames = [];
    for (let i = 0; i < crCount; i++) {
      const len = dv.getUint8(off); off++;
      const bytes = new Uint8Array(buf, off, len);
      crNames.push(_decoder.decode(bytes));
      off += len;
    }
    off = (off + 3) & ~3;

    // typeIds: uint8[siteCount]
    siteTypes = new Uint8Array(buf, off, siteCount);
    off += siteCount;
    off = (off + 3) & ~3;

    // crIds: uint16[siteCount]
    siteCRs = new Uint16Array(buf, off, siteCount);
    off += siteCount * 2;
    off = (off + 3) & ~3;

    // xs: int32[siteCount]
    siteXs = new Int32Array(buf, off, siteCount);
    off += siteCount * 4;

    // ys: int32[siteCount]
    siteYs = new Int32Array(buf, off, siteCount);
    off += siteCount * 4;

    // nameOffsets: uint32[siteCount+1]
    _nameOffsets = new Uint32Array(buf, off, siteCount + 1);
    off += (siteCount + 1) * 4;

    // nameData: raw UTF-8 bytes (rest of file)
    _nameData = new Uint8Array(buf, off);

    console.timeEnd('decode');
    const decodeMs = performance.now() - loadStart - fetchMs;

    console.time('init');
    init();
    console.timeEnd('init');
    const totalMs = performance.now() - loadStart;

    console.log(`Binary load: fetch=${fetchMs.toFixed(0)}ms, decode=${decodeMs.toFixed(0)}ms, total=${totalMs.toFixed(0)}ms, ${siteCount} sites`);
    document.getElementById('info-sites').textContent = `Sites: ${siteCount.toLocaleString()} (loaded in ${totalMs.toFixed(0)}ms)`;
  } catch(e) {
    console.error('Failed to load data:', e);
    document.body.innerHTML = '<h1 style="color:red;padding:40px">Error: Place {{DATA_FILE}} in the same directory and serve via HTTP.<br>' + e.message + '</h1>';
    return;
  }
}

function init() {
  deviceMinX = Infinity; deviceMaxX = -Infinity;
  deviceMinY = Infinity; deviceMaxY = -Infinity;
  for (let i = 0; i < siteCount; i++) {
    const x = siteXs[i], y = siteYs[i];
    if (x < deviceMinX) deviceMinX = x;
    if (x > deviceMaxX) deviceMaxX = x;
    if (y < deviceMinY) deviceMinY = y;
    if (y > deviceMaxY) deviceMaxY = y;
  }

  // Build typeSiteIndices: typeName → Uint32Array of site indices
  const typeCounts = new Uint32Array(typeNames.length);
  for (let i = 0; i < siteCount; i++) typeCounts[siteTypes[i]]++;
  const typeOffsets = new Uint32Array(typeNames.length);
  const typeArrays = {};
  for (let t = 0; t < typeNames.length; t++) {
    typeArrays[typeNames[t]] = new Uint32Array(typeCounts[t]);
    typeOffsets[t] = 0;
  }
  for (let i = 0; i < siteCount; i++) {
    const ti = siteTypes[i];
    const name = typeNames[ti];
    typeArrays[name][typeOffsets[ti]++] = i;
  }
  typeSiteIndices = typeArrays;

  buildSpatialGrid();

  // Clock regions
  clockRegions = {};
  for (let i = 0; i < siteCount; i++) {
    const crName = crNames[siteCRs[i]];
    if (!crName) continue;
    if (!clockRegions[crName]) clockRegions[crName] = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity, count: 0 };
    const cr = clockRegions[crName];
    const x = siteXs[i], y = siteYs[i];
    if (x < cr.minX) cr.minX = x;
    if (x > cr.maxX) cr.maxX = x;
    if (y < cr.minY) cr.minY = y;
    if (y > cr.maxY) cr.maxY = y;
    cr.count++;
  }

  // Per-type bounding boxes for viewport culling
  typeBounds = {};
  for (let i = 0; i < siteCount; i++) {
    const tName = typeNames[siteTypes[i]];
    const x = siteXs[i], y = siteYs[i];
    let tb = typeBounds[tName];
    if (!tb) { tb = { minX: x, maxX: x, minY: y, maxY: y }; typeBounds[tName] = tb; }
    else { if (x < tb.minX) tb.minX = x; if (x > tb.maxX) tb.maxX = x; if (y < tb.minY) tb.minY = y; if (y > tb.maxY) tb.maxY = y; }
  }

  // SLR bounding boxes from clock regions
  slrBounds = {};
  for (const [crName, cr] of Object.entries(clockRegions)) {
    const slr = crName.match(/^(S\d+)/)?.[1];
    if (!slr) continue;
    if (!slrBounds[slr]) slrBounds[slr] = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity, count: 0 };
    const sb = slrBounds[slr];
    if (cr.minX < sb.minX) sb.minX = cr.minX;
    if (cr.maxX > sb.maxX) sb.maxX = cr.maxX;
    if (cr.minY < sb.minY) sb.minY = cr.minY;
    if (cr.maxY > sb.maxY) sb.maxY = cr.maxY;
    sb.count += cr.count;
  }

  for (const t of Object.keys(TYPE_CONFIG)) visible[t] = true;
  for (const t of typeNames) {
    if (!TYPE_CONFIG[t]) TYPE_CONFIG[t] = { color: '#9e9e9e', category: 'Other', shape: 'rect' };
    if (visible[t] === undefined) visible[t] = true;
  }

  // Precompute RGBA for ImageData pixel writes
  for (const [t, cfg] of Object.entries(TYPE_CONFIG)) {
    _typeRGBA[t] = _parseHexColor(cfg.color);
  }

  canvas = document.getElementById('canvas');
  ctx = canvas.getContext('2d', { willReadFrequently: true });
  resizeCanvas();
  resetView();
  buildLegend();
  buildSLRFilter();
  buildCRFilter();
  buildOverlayPanel();
  initOverlayHighlights();
  setupEvents();
  render();
  document.getElementById('info-sites').textContent = `Sites: ${siteCount.toLocaleString()}`;
}

function resizeCanvas() {
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}

function resetView() {
  const cw = canvas.clientWidth, ch = canvas.clientHeight - 28;
  const dw = deviceMaxX - deviceMinX || 1, dh = deviceMaxY - deviceMinY || 1;
  const pad = 40;
  scale = Math.min((cw - pad * 2) / dw, (ch - pad * 2) / dh);
  const cx = (deviceMinX + deviceMaxX) / 2;
  const cy = (deviceMinY + deviceMaxY) / 2;
  offsetX = cw / 2 - cx * scale;
  offsetY = ch / 2 + cy * scale;
}

function toScreenX(x) { return x * scale + offsetX; }
function toScreenY(y) { return -y * scale + offsetY; }
function toDeviceX(sx) { return (sx - offsetX) / scale; }
function toDeviceY(sy) { return -(sy - offsetY) / scale; }

function buildLegend() {
  const legend = document.getElementById('legend');
  const categories = {};
  for (const [type, cfg] of Object.entries(TYPE_CONFIG)) {
    if (!categories[cfg.category]) categories[cfg.category] = [];
    const count = typeSiteIndices[type]?.length || 0;
    categories[cfg.category].push({ type, color: cfg.color, count });
  }

  legend.innerHTML = '';
  for (const [cat, items] of Object.entries(categories)) {
    const hdr = document.createElement('div');
    hdr.className = 'category-header';
    hdr.innerHTML = `<h3>${cat}</h3><span class="toggle-all">toggle</span>`;
    hdr.querySelector('.toggle-all').onclick = (e) => {
      e.stopPropagation();
      const allOn = items.every(i => visible[i.type]);
      items.forEach(i => visible[i.type] = !allOn);
      updateLegendState();
      render();
    };
    legend.appendChild(hdr);

    for (const item of items) {
      if (item.count === 0) continue;
      const div = document.createElement('div');
      div.className = 'legend-item';
      div.dataset.type = item.type;
      div.innerHTML = `<div class="legend-swatch" style="background:${item.color}"></div>
        <span class="legend-label">${item.type}</span>
        <span class="legend-count">${item.count.toLocaleString()}</span>`;
      let clickTimer = null;
      div.onclick = () => {
        if (clickTimer) clearTimeout(clickTimer);
        clickTimer = setTimeout(() => { visible[item.type] = !visible[item.type]; updateLegendState(); render(); }, 250);
      };
      div.ondblclick = (e) => {
        if (clickTimer) { clearTimeout(clickTimer); clickTimer = null; }
        e.stopPropagation();
        if (focusedType === item.type) { focusedType = null; }
        else { focusedType = item.type; visible[item.type] = true; }
        updateLegendState();
        render();
      };
      legend.appendChild(div);
    }
  }
}

function updateLegendState() {
  document.querySelectorAll('.legend-item').forEach(el => {
    el.classList.toggle('disabled', !visible[el.dataset.type]);
    el.classList.toggle('focused', focusedType === el.dataset.type);
    el.style.color = focusedType === el.dataset.type ? TYPE_CONFIG[el.dataset.type]?.color || '' : '';
  });
}

function buildSLRFilter() {
  const container = document.getElementById('slr-options');
  container.innerHTML = '';
  if (!slrBounds || Object.keys(slrBounds).length <= 1) {
    document.getElementById('slr-filter').style.display = 'none';
    return;
  }
  const slrColors = { S0: '#4fc3f7', S1: '#66bb6a', S2: '#ff9800', S3: '#e94560' };
  const allBtn = document.createElement('div');
  allBtn.className = 'slr-btn active';
  allBtn.style.borderColor = '#888';
  allBtn.style.background = '#e94560';
  allBtn.textContent = 'All';
  allBtn.onclick = () => { selectedSLRs.clear(); selectedCRs.clear(); updateSLRButtons(); updateCRButtons(); buildCRFilter(); render(); };
  container.appendChild(allBtn);
  for (const slr of Object.keys(slrBounds).sort()) {
    const btn = document.createElement('div');
    const col = slrColors[slr] || '#ffffff';
    btn.className = 'slr-btn';
    btn.textContent = slr;
    btn.dataset.slr = slr;
    btn.style.borderColor = col;
    btn.title = `${slrBounds[slr].count.toLocaleString()} sites`;
    btn.onclick = () => {
      if (selectedSLRs.has(slr)) selectedSLRs.delete(slr);
      else selectedSLRs.add(slr);
      selectedCRs.clear();
      updateSLRButtons(); buildCRFilter(); render();
    };
    container.appendChild(btn);
  }
}

function updateSLRButtons() {
  document.querySelectorAll('.slr-btn').forEach(btn => {
    const slrColors = { S0: '#4fc3f7', S1: '#66bb6a', S2: '#ff9800', S3: '#e94560' };
    if (!btn.dataset.slr) {
      const isActive = selectedSLRs.size === 0;
      btn.classList.toggle('active', isActive);
      btn.style.background = isActive ? '#e94560' : '#0f3460';
    } else {
      const isActive = selectedSLRs.has(btn.dataset.slr);
      btn.classList.toggle('active', isActive);
      btn.style.background = isActive ? (slrColors[btn.dataset.slr] || '#fff') : '#0f3460';
    }
  });
}

function buildCRFilter() {
  const container = document.getElementById('cr-options');
  container.innerHTML = '';
  const allBtn = document.createElement('div');
  allBtn.className = 'cr-btn active';
  allBtn.textContent = 'All';
  allBtn.onclick = () => { selectedCRs.clear(); updateCRButtons(); render(); };
  container.appendChild(allBtn);
  let crNamesList = Object.keys(clockRegions).sort((a, b) => {
    const [ax, ay] = a.replace('X','').split('Y').map(Number);
    const [bx, by] = b.replace('X','').split('Y').map(Number);
    return ay !== by ? by - ay : ax - bx;
  });
  if (selectedSLRs.size > 0) {
    crNamesList = crNamesList.filter(cr => {
      const slr = cr.match(/^(S\d+)/)?.[1];
      return slr && selectedSLRs.has(slr);
    });
  }
  for (const cr of crNamesList) {
    const btn = document.createElement('div');
    btn.className = 'cr-btn';
    btn.textContent = cr;
    btn.dataset.cr = cr;
    btn.title = `${clockRegions[cr].count.toLocaleString()} sites`;
    btn.onclick = () => {
      if (selectedCRs.has(cr)) selectedCRs.delete(cr);
      else selectedCRs.add(cr);
      updateCRButtons(); render();
    };
    container.appendChild(btn);
  }
  document.getElementById('cb-show-cr').onchange = (e) => { showCRBounds = e.target.checked; render(); };

  const clkCtrl = document.getElementById('clk-track-controls');
  if (!CLK_TRACK_DATA) {
    clkCtrl.style.display = 'none';
    return;
  }
  document.getElementById('cb-show-clk-tracks').onchange = (e) => {
    showClkTracks = e.target.checked;
    document.getElementById('clk-track-legend').style.display = showClkTracks ? 'flex' : 'none';
    render();
  };
  const trackTypes = [
    { key: 'hroute', label: 'HROUTE', color: '#ff6b6b' },
    { key: 'hdistr', label: 'HDISTR', color: '#ffd93d' },
    { key: 'leaf',   label: 'LEAF',   color: '#6bcb77' },
    { key: 'vroute', label: 'VROUTE', color: '#4d96ff' },
  ];
  const legendDiv = document.getElementById('clk-track-legend');
  legendDiv.innerHTML = '';
  for (const tt of trackTypes) {
    const btn = document.createElement('div');
    btn.className = 'clk-track-btn active';
    btn.dataset.track = tt.key;
    btn.style.color = tt.color;
    btn.innerHTML = `<span class="swatch" style="background:${tt.color}"></span>${tt.label}`;
    btn.onclick = () => {
      clkTrackVisible[tt.key] = !clkTrackVisible[tt.key];
      btn.classList.toggle('active', clkTrackVisible[tt.key]);
      btn.classList.toggle('disabled', !clkTrackVisible[tt.key]);
      render();
    };
    legendDiv.appendChild(btn);
  }
}

function updateCRButtons() {
  document.querySelectorAll('.cr-btn').forEach(btn => {
    if (!btn.dataset.cr) btn.classList.toggle('active', selectedCRs.size === 0);
    else btn.classList.toggle('active', selectedCRs.has(btn.dataset.cr));
  });
}

function drawClockTracks(cw, ch) {
  if (!CLK_TRACK_DATA) return;
  const T = CLK_TRACK_DATA;

  if (clkTrackVisible.hroute)
  for (const [crName, cr] of Object.entries(clockRegions)) {
    const crMidY = (cr.minY + cr.maxY) / 2;
    const crHeight = cr.maxY - cr.minY;
    if (crHeight < 100) continue;
    const hrouteSpacing = crHeight * 0.02;
    const hrouteStartY = crMidY + (T.tracksPerCR / 2) * hrouteSpacing;
    const sx1 = toScreenX(cr.minX), sx2 = toScreenX(cr.maxX);
    if (sx2 < -10 || sx1 > cw + 10) continue;
    ctx.globalAlpha = 0.35;
    ctx.strokeStyle = '#ff6b6b';
    ctx.lineWidth = Math.max(0.5, scale * 5);
    for (let i = 0; i < T.tracksPerCR; i++) {
      const y = hrouteStartY - i * hrouteSpacing;
      const sy = toScreenY(y);
      if (sy < -10 || sy > ch + 10) continue;
      ctx.beginPath(); ctx.moveTo(sx1, sy); ctx.lineTo(sx2, sy); ctx.stroke();
    }
  }

  if (clkTrackVisible.hdistr)
  for (const [crName, cr] of Object.entries(clockRegions)) {
    const crMidY = (cr.minY + cr.maxY) / 2;
    const crHeight = cr.maxY - cr.minY;
    if (crHeight < 100) continue;
    const hdistrSpacing = crHeight * 0.015;
    const hdistrStartY = crMidY + crHeight * 0.3 + (T.tracksPerCR / 2) * hdistrSpacing;
    const sx1 = toScreenX(cr.minX), sx2 = toScreenX(cr.maxX);
    if (sx2 < -10 || sx1 > cw + 10) continue;
    ctx.globalAlpha = 0.2;
    ctx.strokeStyle = '#ffd93d';
    ctx.lineWidth = Math.max(0.3, scale * 3);
    for (let i = 0; i < T.tracksPerCR; i++) {
      const y = hdistrStartY - i * hdistrSpacing;
      const sy = toScreenY(y);
      if (sy < -10 || sy > ch + 10) continue;
      ctx.beginPath(); ctx.moveTo(sx1, sy); ctx.lineTo(sx2, sy); ctx.stroke();
    }
  }

  if (clkTrackVisible.vroute) {
    ctx.globalAlpha = 0.3;
    ctx.strokeStyle = '#4d96ff';
    ctx.lineWidth = Math.max(0.5, scale * 8);
    for (const bx of (T.bufgceXs || [])) {
      const sx = toScreenX(bx);
      if (sx < -10 || sx > cw + 10) continue;
      const sy1 = toScreenY(T.bufgceY || deviceMinY);
      const sy2 = toScreenY(deviceMaxY);
      ctx.beginPath(); ctx.moveTo(sx, sy1); ctx.lineTo(sx, sy2); ctx.stroke();
    }
    ctx.lineWidth = Math.max(0.3, scale * 5);
    ctx.globalAlpha = 0.2;
    for (const bx of (T.bufgFabricXs || [])) {
      const sx = toScreenX(bx);
      if (sx < -10 || sx > cw + 10) continue;
      for (const by of (T.bufgFabricYs || [])) {
        const sy1 = toScreenY(by);
        const sy2 = toScreenY(by + 3800);
        ctx.beginPath(); ctx.moveTo(sx, sy1); ctx.lineTo(sx, sy2); ctx.stroke();
      }
    }
  }

  if (clkTrackVisible.leaf) {
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = '#6bcb77';
    for (const band of (T.bufdivLeaf || [])) {
      const sx1 = toScreenX(band.minX), sx2 = toScreenX(band.maxX);
      const sy1 = toScreenY(band.maxY), sy2 = toScreenY(band.minY);
      if (sx2 < -10 || sx1 > cw + 10 || sy2 < -10 || sy1 > ch + 10) continue;
      const bandHeight = Math.max(2, sy2 - sy1);
      ctx.fillRect(sx1, sy1, sx2 - sx1, bandHeight);
      ctx.strokeStyle = '#6bcb77';
      ctx.lineWidth = Math.max(0.3, scale * 3);
      ctx.globalAlpha = 0.5;
      for (const lx of (T.leafColumnXs || [])) {
        if (lx < band.minX || lx > band.maxX) continue;
        const slx = toScreenX(lx);
        ctx.beginPath(); ctx.moveTo(slx, sy1); ctx.lineTo(slx, sy2); ctx.stroke();
      }
      ctx.globalAlpha = 0.4;
      ctx.fillStyle = '#6bcb77';
      const labelSize = Math.max(6, Math.min(10, scale * 200));
      if (labelSize >= 7) {
        ctx.font = `${labelSize}px monospace`;
        ctx.fillStyle = '#6bcb77';
        ctx.globalAlpha = 0.7;
        ctx.textAlign = 'left';
        ctx.fillText(`LEAF ${band.cr} (${band.cols}x${band.rows})`, sx1 + 2, sy1 - 2);
        ctx.globalAlpha = 0.4;
        ctx.fillStyle = '#6bcb77';
      }
    }
  }

  ctx.globalAlpha = 1.0;
  ctx.textAlign = 'start';
}

function buildOverlayPanel() {
  const container = document.getElementById('overlay-panel');
  if (!container) return;
  const hasOverlay = (OVERLAY_CR_FILLS && Object.keys(OVERLAY_CR_FILLS).length > 0) ||
                     (OVERLAY_RECTS && OVERLAY_RECTS.length > 0) ||
                     (OVERLAY_SITE_HIGHLIGHTS && OVERLAY_SITE_HIGHLIGHTS.length > 0);
  if (!hasOverlay) { container.style.display = 'none'; return; }

  let html = '';
  if (OVERLAY_TITLE) html += `<h3 style="color:#e94560;margin-bottom:6px">${OVERLAY_TITLE}</h3>`;

  if (OVERLAY_LEGEND && OVERLAY_LEGEND.length > 0) {
    for (const entry of OVERLAY_LEGEND) {
      const swatch = entry.shape === 'dash'
        ? `<div style="width:14px;height:14px;border:2px dashed ${entry.color};border-radius:2px;flex-shrink:0"></div>`
        : entry.shape === 'circle'
        ? `<div style="width:14px;height:14px;border-radius:50%;background:${entry.color};flex-shrink:0"></div>`
        : `<div class="legend-swatch" style="background:${entry.color}"></div>`;
      html += `<div class="legend-item">${swatch}<span class="legend-label">${entry.label}</span></div>`;
    }
  }
  container.innerHTML = html;
}

function initOverlayHighlights() {
  _highlightSets = [];
  if (!OVERLAY_SITE_HIGHLIGHTS || OVERLAY_SITE_HIGHLIGHTS.length === 0) return;
  // Build name index if not already built
  if (!_nameIndex) {
    _nameIndex = {};
    for (let i = 0; i < siteCount; i++) _nameIndex[getSiteName(i).toUpperCase()] = i;
  }
  for (const hl of OVERLAY_SITE_HIGHLIGHTS) {
    const indices = [];
    const pat = hl.pattern.toUpperCase();
    if (pat.includes('*') || pat.includes('?')) {
      // Glob pattern → regex
      const re = new RegExp('^' + pat.replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
      for (const [name, idx] of Object.entries(_nameIndex)) {
        if (re.test(name)) indices.push(idx);
      }
    } else {
      // Exact match
      const idx = _nameIndex[pat];
      if (idx !== undefined) indices.push(idx);
    }
    _highlightSets.push({ indices, color: hl.color, label: hl.label });
  }
}

function drawOverlayCRFills(cw, ch) {
  if (!OVERLAY_CR_FILLS || Object.keys(OVERLAY_CR_FILLS).length === 0) return;
  const pad = 15;
  for (const [crName, cfg] of Object.entries(OVERLAY_CR_FILLS)) {
    const cr = clockRegions[crName];
    if (!cr) continue;
    const sx1 = toScreenX(cr.minX - pad), sy1 = toScreenY(cr.maxY + pad);
    const sx2 = toScreenX(cr.maxX + pad), sy2 = toScreenY(cr.minY - pad);
    if (sx2 < 0 || sx1 > cw || sy2 < 0 || sy1 > ch) continue;
    ctx.fillStyle = cfg.fill;
    ctx.fillRect(sx1, sy1, sx2 - sx1, sy2 - sy1);
    // Label in center
    if (cfg.label) {
      const labelSize = Math.max(7, Math.min(12, scale * 250));
      ctx.font = `bold ${labelSize}px sans-serif`;
      ctx.fillStyle = cfg.labelColor || '#fff';
      ctx.globalAlpha = 0.9;
      ctx.textAlign = 'center';
      ctx.fillText(cfg.label, (sx1 + sx2) / 2, (sy1 + sy2) / 2 + labelSize / 3);
      ctx.globalAlpha = 1.0;
      ctx.textAlign = 'start';
    }
  }
}

function drawOverlayRects(cw, ch) {
  if (!OVERLAY_RECTS || OVERLAY_RECTS.length === 0) return;
  for (const r of OVERLAY_RECTS) {
    const sx1 = toScreenX(r.x1), sy1 = toScreenY(r.y2); // y flipped
    const sx2 = toScreenX(r.x2), sy2 = toScreenY(r.y1);
    if (sx2 < 0 || sx1 > cw || sy2 < 0 || sy1 > ch) continue;
    if (r.fill) {
      ctx.fillStyle = r.fill;
      ctx.fillRect(sx1, sy1, sx2 - sx1, sy2 - sy1);
    }
    ctx.strokeStyle = r.color || '#e94560';
    ctx.lineWidth = r.lineWidth || 2;
    if (r.dash) ctx.setLineDash(r.dash === true ? [6, 4] : r.dash);
    ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1);
    ctx.setLineDash([]);
    if (r.label) {
      const labelSize = Math.max(8, Math.min(12, scale * 200));
      ctx.font = `bold ${labelSize}px sans-serif`;
      ctx.fillStyle = r.color || '#e94560';
      ctx.globalAlpha = 0.9;
      ctx.fillText(r.label, sx1 + 3, sy1 - 3);
      ctx.globalAlpha = 1.0;
    }
  }
}

function drawOverlayHighlights(cw, ch) {
  if (_highlightSets.length === 0) return;
  const baseSize = Math.max(1, Math.min(6, scale * 15));
  const sz = Math.max(baseSize * 1.5, 4);
  for (const hs of _highlightSets) {
    ctx.fillStyle = hs.color;
    ctx.shadowColor = hs.color;
    ctx.shadowBlur = 8;
    for (const idx of hs.indices) {
      const sx = toScreenX(siteXs[idx]), sy = toScreenY(siteYs[idx]);
      if (sx < -10 || sx > cw + 10 || sy < -10 || sy > ch + 10) continue;
      ctx.beginPath(); ctx.arc(sx, sy, sz, 0, Math.PI * 2); ctx.fill();
    }
    ctx.shadowBlur = 0;
  }
}

function scheduleRender() {
  if (_rafPending) return;
  _rafPending = true;
  requestAnimationFrame(() => { _rafPending = false; _renderImpl(); });
}

function _renderImpl() {
  const cw = canvas.clientWidth, ch = canvas.clientHeight;
  ctx.clearRect(0, 0, cw, ch);

  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, cw, ch);

  // Device outline
  const dx1 = toScreenX(deviceMinX) - 10, dy1 = toScreenY(deviceMaxY) - 10;
  const dx2 = toScreenX(deviceMaxX) + 10, dy2 = toScreenY(deviceMinY) + 10;
  ctx.strokeStyle = '#0f3460';
  ctx.lineWidth = 1;
  ctx.strokeRect(dx1, dy1, dx2 - dx1, dy2 - dy1);

  // SLR boundaries
  if (slrBounds && Object.keys(slrBounds).length > 1) {
    const slrColors = { S0: '#4fc3f7', S1: '#66bb6a', S2: '#ff9800', S3: '#e94560' };
    const pad = 30;
    for (const [slrName, sb] of Object.entries(slrBounds)) {
      const sx1 = toScreenX(sb.minX - pad), sy1 = toScreenY(sb.maxY + pad);
      const sx2 = toScreenX(sb.maxX + pad), sy2 = toScreenY(sb.minY - pad);
      const col = slrColors[slrName] || '#ffffff';
      ctx.strokeStyle = col;
      ctx.lineWidth = 3;
      ctx.setLineDash([]);
      ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1);
      const labelSize = Math.max(12, Math.min(24, scale * 800));
      ctx.font = `bold ${labelSize}px monospace`;
      ctx.fillStyle = col;
      ctx.globalAlpha = 0.85;
      ctx.textAlign = 'center';
      ctx.fillText(slrName, (sx1 + sx2) / 2, sy1 + labelSize + 8);
      ctx.globalAlpha = 1.0;
    }
    ctx.textAlign = 'start';
  }

  // Clock region boundaries
  if (showCRBounds) {
    const pad = 15;
    for (const [crName, cr] of Object.entries(clockRegions)) {
      const sx1 = toScreenX(cr.minX - pad), sy1 = toScreenY(cr.maxY + pad);
      const sx2 = toScreenX(cr.maxX + pad), sy2 = toScreenY(cr.minY - pad);
      const isSelected = selectedCRs.has(crName);
      ctx.strokeStyle = isSelected ? '#e94560' : '#1e3a5f';
      ctx.lineWidth = isSelected ? 2 : 1;
      ctx.setLineDash(isSelected ? [] : [4, 4]);
      ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1);
      ctx.setLineDash([]);
      const labelSize = Math.max(8, Math.min(14, scale * 300));
      ctx.font = `bold ${labelSize}px monospace`;
      ctx.fillStyle = isSelected ? '#e94560' : '#334466';
      ctx.textAlign = 'center';
      ctx.fillText(crName, (sx1 + sx2) / 2, sy1 + labelSize + 4);
    }
    ctx.textAlign = 'start';
  }

  // Clock tracks overlay
  if (showClkTracks) drawClockTracks(cw, ch);

  // Overlay: CR background fills (drawn before sites so sites appear on top)
  drawOverlayCRFills(cw, ch);

  // Determine point size based on zoom
  const baseSize = Math.max(1, Math.min(6, scale * 15));

  // Precompute which CRs pass the SLR+CR filter
  const activeCRSet = new Set();
  if (selectedSLRs.size === 0 && selectedCRs.size === 0) {
    // no filter — all pass
  } else {
    for (const crName of Object.keys(clockRegions)) {
      const slr = crName.match(/^(S\d+)/)?.[1];
      const slrOk = selectedSLRs.size === 0 || (slr && selectedSLRs.has(slr));
      const crOk = selectedCRs.size === 0 || selectedCRs.has(crName);
      if (slrOk && crOk) activeCRSet.add(crName);
    }
  }
  const noFilter = selectedSLRs.size === 0 && selectedCRs.size === 0;

  // Determine point size based on zoom
  const use1px = baseSize <= 1.5;

  // === ImageData fast-path: direct pixel writes for 1px + no filter ===
  if (use1px && noFilter && !focusedType) {
    const dpr = devicePixelRatio;
    const pw = canvas.width, ph = canvas.height; // physical pixels
    const imgData = ctx.getImageData(0, 0, pw, ph);
    const pixels = imgData.data; // Uint8ClampedArray RGBA
    const stride = pw * 4;

    for (const type of Object.keys(TYPE_CONFIG)) {
      if (!visible[type]) continue;
      const indices = typeSiteIndices[type];
      if (!indices || indices.length === 0) continue;
      const tb = typeBounds[type];
      if (tb) {
        const tbx1 = toScreenX(tb.minX), tbx2 = toScreenX(tb.maxX);
        const tby1 = toScreenY(tb.maxY), tby2 = toScreenY(tb.minY);
        if (tbx2 < 0 || tbx1 > cw || tby2 < 0 || tby1 > ch) continue;
      }
      const [r, g, b] = _typeRGBA[type] || [158, 158, 158];
      for (let j = 0; j < indices.length; j++) {
        const idx = indices[j];
        const px = (siteXs[idx] * scale + offsetX) * dpr | 0;
        const py = (-siteYs[idx] * scale + offsetY) * dpr | 0;
        if (px < 0 || px >= pw || py < 0 || py >= ph) continue;
        const off = py * stride + px * 4;
        pixels[off] = r;
        pixels[off + 1] = g;
        pixels[off + 2] = b;
        pixels[off + 3] = 255;
      }
    }
    ctx.putImageData(imgData, 0, 0);

    // Skip the normal drawOrder loop — jump to post-render (hovered, search, rubber-band)
  } else {
  // === Normal canvas render path ===

  // Draw sites by type
  const drawOrder = {{DRAW_ORDER}};

  for (const type of drawOrder) {
    if (!visible[type]) continue;
    if (focusedType === type) continue;
    const cfg = TYPE_CONFIG[type];
    if (!cfg) continue;
    const tb = typeBounds[type];
    if (tb) {
      const tbx1 = toScreenX(tb.minX), tbx2 = toScreenX(tb.maxX);
      const tby1 = toScreenY(tb.maxY), tby2 = toScreenY(tb.minY);
      if (tbx2 < -20 || tbx1 > cw + 20 || tby2 < -20 || tby1 > ch + 20) continue;
    }
    const indices = typeSiteIndices[type];
    if (!indices || indices.length === 0) continue;
    const sz = (type.startsWith('SLICE') || type.startsWith('RAMB18') || type.startsWith('CLB')) ? baseSize : baseSize * 1.3;

    const fastAlpha = noFilter && !focusedType;
    if (fastAlpha) { ctx.fillStyle = cfg.color; ctx.globalAlpha = 1.0; }

    const use1pxType = sz <= 1.5;

    for (let j = 0; j < indices.length; j++) {
      const i = indices[j];
      const sx = toScreenX(siteXs[i]), sy = toScreenY(siteYs[i]);
      if (sx < -10 || sx > cw + 10 || sy < -10 || sy > ch + 10) continue;
      if (!fastAlpha) {
        const inCR = noFilter || activeCRSet.has(crNames[siteCRs[i]]);
        ctx.fillStyle = cfg.color;
        ctx.globalAlpha = inCR ? (focusedType ? 0.12 : 1.0) : 0.08;
      }

      if (use1pxType) {
        ctx.fillRect(sx | 0, sy | 0, 1, 1);
      } else if (cfg.shape === 'circle') {
        ctx.beginPath(); ctx.arc(sx, sy, sz * 0.6, 0, Math.PI * 2); ctx.fill();
      } else if (cfg.shape === 'diamond') {
        ctx.beginPath(); ctx.moveTo(sx, sy - sz); ctx.lineTo(sx + sz * 0.7, sy);
        ctx.lineTo(sx, sy + sz); ctx.lineTo(sx - sz * 0.7, sy); ctx.closePath(); ctx.fill();
      } else if (cfg.shape === 'tall') {
        ctx.fillRect(sx - sz * 0.5, sy - sz, sz, sz * 2);
      } else {
        ctx.fillRect(sx - sz / 2, sy - sz / 2, sz, sz);
      }
    }
  }

  // Draw focused type LAST with boosted size and glow
  if (focusedType && visible[focusedType]) {
    const cfg = TYPE_CONFIG[focusedType];
    if (cfg) {
      const indices = typeSiteIndices[focusedType];
      if (indices && indices.length > 0) {
        const sz = Math.max(baseSize * 1.3, 6);
        ctx.shadowColor = cfg.color;
        ctx.shadowBlur = 10;
        for (let j = 0; j < indices.length; j++) {
          const i = indices[j];
          const sx = toScreenX(siteXs[i]), sy = toScreenY(siteYs[i]);
          if (sx < -10 || sx > cw + 10 || sy < -10 || sy > ch + 10) continue;
          const inCR = noFilter || activeCRSet.has(crNames[siteCRs[i]]);
          ctx.fillStyle = inCR ? '#fff' : cfg.color;
          ctx.globalAlpha = inCR ? 1.0 : 0.15;
          if (!inCR) ctx.shadowBlur = 0; else ctx.shadowBlur = 10;
          if (cfg.shape === 'circle') {
            ctx.beginPath(); ctx.arc(sx, sy, sz * 0.6, 0, Math.PI * 2); ctx.fill();
          } else if (cfg.shape === 'diamond') {
            ctx.beginPath(); ctx.moveTo(sx, sy - sz); ctx.lineTo(sx + sz * 0.7, sy);
            ctx.lineTo(sx, sy + sz); ctx.lineTo(sx - sz * 0.7, sy); ctx.closePath(); ctx.fill();
          } else if (cfg.shape === 'tall') {
            ctx.fillRect(sx - sz * 0.5, sy - sz, sz, sz * 2);
          } else {
            ctx.fillRect(sx - sz / 2, sy - sz / 2, sz, sz);
          }
        }
        ctx.shadowBlur = 0;
      }
    }
  }
  ctx.globalAlpha = 1.0;
  } // end else (normal canvas render path)

  // Overlay: rectangles and site highlights (drawn after sites, before hover/search)
  drawOverlayRects(cw, ch);
  drawOverlayHighlights(cw, ch);

  // Highlight searched site
  if (searchHighlightIdx >= 0) {
    const sx = toScreenX(siteXs[searchHighlightIdx]), sy = toScreenY(siteYs[searchHighlightIdx]);
    ctx.strokeStyle = '#ff0';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(sx, sy, baseSize * 3, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = '#f00';
    ctx.beginPath();
    ctx.moveTo(sx - baseSize * 4, sy); ctx.lineTo(sx + baseSize * 4, sy);
    ctx.moveTo(sx, sy - baseSize * 4); ctx.lineTo(sx, sy + baseSize * 4);
    ctx.stroke();
  }

  // Hovered site
  if (hoveredIdx >= 0) {
    const sx = toScreenX(siteXs[hoveredIdx]), sy = toScreenY(siteYs[hoveredIdx]);
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(sx, sy, baseSize * 2, 0, Math.PI * 2); ctx.stroke();
  }

  // Rubber-band selection rectangle
  if (isSelecting) {
    const rx = Math.min(selStartX, selCurX), ry = Math.min(selStartY, selCurY);
    const rw = Math.abs(selCurX - selStartX), rh = Math.abs(selCurY - selStartY);
    const zoomOut = selCurX < selStartX;
    ctx.strokeStyle = zoomOut ? '#4d96ff' : '#e94560';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(rx, ry, rw, rh);
    ctx.setLineDash([]);
    ctx.fillStyle = zoomOut ? 'rgba(77, 150, 255, 0.08)' : 'rgba(233, 69, 96, 0.08)';
    ctx.fillRect(rx, ry, rw, rh);
  }

  // Update info bar
  document.getElementById('info-zoom').textContent = `Zoom: ${scale.toFixed(4)}x`;
  if (selectedSLRs.size > 0 || selectedCRs.size > 0) {
    let filterParts = [];
    if (selectedSLRs.size > 0) filterParts.push([...selectedSLRs].sort().join(', '));
    if (selectedCRs.size > 0) filterParts.push([...selectedCRs].sort().join(', '));
    const totalSites = noFilter ? siteCount : [...activeCRSet].reduce((sum, cr) => sum + (clockRegions[cr]?.count || 0), 0);
    document.getElementById('info-sites').textContent = `${filterParts.join(' / ')} (${totalSites.toLocaleString()} sites)`;
  } else {
    document.getElementById('info-sites').textContent = `Sites: ${siteCount.toLocaleString()}`;
  }
}

function render() { scheduleRender(); }

function setupEvents() {
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zf = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const mx = e.offsetX, my = e.offsetY;
    const dx = toDeviceX(mx), dy = toDeviceY(my);
    scale *= zf;
    offsetX = mx - dx * scale;
    offsetY = my + dy * scale;
    render();
  }, { passive: false });

  canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  canvas.addEventListener('mousedown', (e) => {
    if (e.button === 2) {
      isDragging = true;
      dragStartX = e.offsetX; dragStartY = e.offsetY;
      dragOffsetX = offsetX; dragOffsetY = offsetY;
      canvas.style.cursor = 'grabbing';
    } else if (e.button === 0) {
      isSelecting = true;
      selStartX = e.offsetX; selStartY = e.offsetY;
      selCurX = e.offsetX; selCurY = e.offsetY;
      canvas.style.cursor = 'crosshair';
    }
  });
  window.addEventListener('mousemove', (e) => {
    if (isSelecting) {
      const rect = canvas.getBoundingClientRect();
      selCurX = e.clientX - rect.left;
      selCurY = e.clientY - rect.top;
      render();
    }
    if (isDragging) {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      offsetX = dragOffsetX + (mx - dragStartX);
      offsetY = dragOffsetY + (my - dragStartY);
      render();
    }
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const devX = toDeviceX(mx), devY = toDeviceY(my);
    document.getElementById('info-pos').textContent = `RPM: ${Math.round(devX)}, ${Math.round(devY)}`;

    const baseSize = Math.max(1, Math.min(6, scale * 15));
    const threshold = baseSize * 3 / scale;
    const nearest = findNearest(devX, devY, threshold);

    if (nearest !== hoveredIdx) {
      hoveredIdx = nearest;
      const tooltip = document.getElementById('tooltip');
      if (nearest >= 0) {
        const typeName = typeNames[siteTypes[nearest]];
        const cfg = TYPE_CONFIG[typeName] || {};
        const name = getSiteName(nearest);
        const crName = crNames[siteCRs[nearest]];
        tooltip.innerHTML = `<b style="color:${cfg.color || '#fff'}">${typeName}</b><br>${name}<br>RPM: (${siteXs[nearest]}, ${siteYs[nearest]})${crName ? '<br>CR: ' + crName : ''}`;
        tooltip.style.display = 'block';
      } else {
        tooltip.style.display = 'none';
      }
      render();
    }
    if (hoveredIdx >= 0) {
      const tooltip = document.getElementById('tooltip');
      tooltip.style.left = (e.clientX - canvas.getBoundingClientRect().left + 15) + 'px';
      tooltip.style.top = (e.clientY - canvas.getBoundingClientRect().top - 10) + 'px';
    }
  });
  window.addEventListener('mouseup', () => {
    if (isSelecting) {
      isSelecting = false;
      const sw = Math.abs(selCurX - selStartX), sh = Math.abs(selCurY - selStartY);
      if (sw > 5 && sh > 5) {
        const zoomOut = selCurX < selStartX;
        const x0 = Math.min(selStartX, selCurX), x1 = Math.max(selStartX, selCurX);
        const y0 = Math.min(selStartY, selCurY), y1 = Math.max(selStartY, selCurY);
        const cw = canvas.clientWidth, ch = canvas.clientHeight - 28;
        const cx = toDeviceX((x0 + x1) / 2), cy = toDeviceY((y0 + y1) / 2);
        if (zoomOut) {
          const factor = Math.max(cw / sw, ch / sh);
          scale /= factor;
        } else {
          const devX0 = toDeviceX(x0), devX1 = toDeviceX(x1);
          const devY0 = toDeviceY(y0), devY1 = toDeviceY(y1);
          const devW = Math.abs(devX1 - devX0), devH = Math.abs(devY1 - devY0);
          const pad = 20;
          scale = Math.min((cw - pad * 2) / devW, (ch - pad * 2) / devH);
        }
        offsetX = cw / 2 - cx * scale;
        offsetY = ch / 2 + cy * scale;
      }
      render();
    }
    isDragging = false;
    canvas.style.cursor = 'crosshair';
  });

  window.addEventListener('resize', () => { resizeCanvas(); resetView(); render(); });

  document.getElementById('btn-reset').onclick = () => { resetView(); render(); };
  document.getElementById('btn-toggle-all').onclick = () => {
    allVisible = !allVisible;
    for (const t of Object.keys(TYPE_CONFIG)) visible[t] = allVisible;
    updateLegendState();
    render();
  };
  document.getElementById('btn-screenshot').onclick = () => {
    const link = document.createElement('a');
    link.download = '{{DEVICE_NAME}}_device_view.png';
    link.href = canvas.toDataURL('image/png');
    link.click();
  };

  document.getElementById('search-box').addEventListener('input', (e) => {
    const q = e.target.value.trim().toUpperCase();
    if (!q) { searchHighlightIdx = -1; render(); return; }
    if (!_nameIndex) {
      _nameIndex = {};
      for (let i = 0; i < siteCount; i++) _nameIndex[getSiteName(i).toUpperCase()] = i;
    }
    const idx = _nameIndex[q];
    if (idx !== undefined) {
      searchHighlightIdx = idx;
      const cw = canvas.clientWidth, ch = canvas.clientHeight;
      offsetX = cw / 2 - siteXs[idx] * scale;
      offsetY = ch / 2 + siteYs[idx] * scale;
      visible[typeNames[siteTypes[idx]]] = true;
      updateLegendState();
      render();
    } else {
      // Try partial match
      let partialIdx = -1;
      for (const [name, i] of Object.entries(_nameIndex)) {
        if (name.includes(q)) { partialIdx = i; break; }
      }
      if (partialIdx >= 0) { searchHighlightIdx = partialIdx; render(); }
      else { searchHighlightIdx = -1; render(); }
    }
  });

  canvas.style.cursor = 'crosshair';
}

loadBinaryData();
</script>
</body>
</html>
```
