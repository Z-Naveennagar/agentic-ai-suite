<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Field Learnings — Hard-Won from Deployments

Operational lessons from actual design failures. These are NOT covered by
`vivado_doc_search` — they encode knowledge that documentation alone does not provide.
Consult during relevant phases (HLS development, board deployment, DMA validation).

---

## Always Inspect the Actual Model, Never Trust the Paper

When implementing ML models (ONNX, TFLite, etc.) in HLS, the published paper architecture
often differs from the shipped model. Before writing any HLS code:
1. Load the ONNX model and inspect actual layer topology (use `onnxruntime` intermediate
   tensor extraction or `netron` visualization)
2. Verify activation functions, normalization axes, and weight shapes against the actual
   graph — not the paper
3. Build a NumPy golden reference that matches the ONNX output to <0.01 max error before
   starting HLS

Example: Magika v3.3's paper described 128-dim embeddings + two Dense layers. The actual
ONNX model had 64-dim embeddings, a Conv1D(kernel=5), two LayerNorms, and GELU activations.
The HLS kernel would have been completely wrong if built from the paper.

## HLS Memory Architecture Must Be Planned Before Coding

For any array larger than ~16KB, explicitly choose BRAM, URAM, or DDR before writing the
kernel. Letting HLS auto-partition will either hang synthesis or produce an unroutable design.

Recommended strategy for ML inference kernels:
- **URAM**: Large intermediate activations (e.g., 512x256 float feature maps)
- **BRAM**: Small tiled working buffers (<16KB, e.g., Conv weight tiles, line buffers)
- **DDR via M_AXI**: Weights too large for on-chip storage (stream in tiles per layer)

## Incremental Hardware Validation Prevents Undiagnosable Failures

When deploying PL designs to embedded boards, validate each layer before adding the next:
1. Load bitstream only — verify PL clocks running (no UIO device yet)
2. Add UIO device in DTBO — verify register read via `devmem 0x<base_addr>`
3. Write a known pattern to a DMA buffer, read it back — verify memory path
4. Then run full inference

Skipping to step 4 means a failure could be in the bitstream, DTBO, AFI config, DMA setup,
or kernel logic. Each step isolates one layer.

## dfx-mgr Persistence Can Brick Kria Boards

On Kria, `xmutil loadapp` persists across reboots via `dfx-mgr`. A bad device tree overlay
(especially incorrect `config-afi` values causing AXI width mismatch) will hang the board
on every boot attempt. Before first `xmutil loadapp` of a new design, validate the DTBO
with a register read test (`sudo devmem 0x<base_addr>`) and know your recovery path
(serial console, SD card removal, or Kria Boot Recovery Tool). See `kria-dynamic-pl-artifacts`
skill Error 6 for detailed recovery procedures.
