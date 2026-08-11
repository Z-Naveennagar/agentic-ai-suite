---
name: workload-partition-advisor
description: >-
  Analyze algorithm workloads and recommend AIE/PL/PS partitioning for AMD Versal
  heterogeneous compute. Computes MACs/sample, storage requirements, and I/O bandwidth;
  compares against AIE architecture limits (AIE, AIE-ML, AIE-ML v2); outputs a
  partitioning proposal with tile estimates, PLIO configuration, and data flow topology.
  Use when: user wants to partition an algorithm across AIE and PL, estimate tile count
  for their design, determine if their workload fits on a target device, analyze
  compute/storage/bandwidth requirements, decide what goes on AI Engine vs. programmable
  logic, or plan system architecture for a DSP algorithm on Versal.
argument-hint: >-
  Provide: algorithm description (or reference model code), data types, sample rates,
  target device and speed grade, performance targets (throughput, latency).
user-invocable: true
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Workload Partition Advisor

Analyze algorithm requirements across three fundamental dimensions — **compute**, **storage**, and **bandwidth** — compare against hardware capability, and recommend an AIE/PL/PS partitioning with tile estimates.

---

## Prerequisites

Before performing any analysis, gather the following from the user. Ask clarifying questions if any are missing.

### Required Inputs

| Input | Description | Example |
|-------|-------------|---------|
| **Algorithm** | Free-form description OR reference model code (Python/MATLAB) | "64-tap FIR filter" or `np.convolve(x, h)` |
| **Data types** | Input/output/coefficient precision | cint16, int32, bfloat16 |
| **Sample rate** | Input sample rate (and output if different) | 1 Gsps, 491.52 Msps |
| **Target device** | Versal device or eval board | VCK190, VEK280, VE2302, XC2VE3504 |
| **Speed grade** | Device speed grade (determines clock) | -1L, -2M, -1M |

### Optional Inputs

| Input | Description | Default |
|-------|-------------|---------|
| **Frame size** | Processing block size | Streaming (sample-by-sample) |
| **Latency target** | Maximum acceptable latency | No constraint |
| **Throughput target** | Minimum throughput | Matches sample rate |
| **Number of channels** | Parallel independent channels | 1 |

---

## Workflow

### Step 1: Algorithm Decomposition

Parse the user's input and identify discrete functional blocks.

#### From free-form text:
- Identify named DSP operations (FIR, FFT, mixer, DDS, correlator, matrix multiply, etc.)
- Extract parameters: tap count, point size, decimation/interpolation factor, etc.

#### From reference model code:
Recognize common patterns and map to DSP primitives:

| Code Pattern | DSP Block | MACs/sample |
|---|---|---|
| `np.convolve(x, h)` or `scipy.signal.lfilter(b, a, x)` | FIR filter | len(h) |
| `np.fft.fft(x, N)` | N-pt FFT | ~(N/2)·log₂(N) butterflies |
| `x * np.exp(1j*2*pi*f*t)` | Mixer/NCO | 4 (complex multiply) |
| `A @ B` or `np.matmul(A, B)` | Matrix multiply | M×N×K |
| `scipy.signal.firwin(N, ...)` followed by filter | FIR filter | N |
| `scipy.signal.decimate(x, M)` | Decimation FIR | taps/M effective |
| Element-wise operations (`+`, `-`, `abs`, `clip`) | Vector ALU | ~1 |
| Bit-shift, XOR, CRC, scrambling | Bit manipulation | → PL candidate |

For complex or unfamiliar code, ask the user to confirm the MAC count per sample.

#### Classification:

Assign each block to a candidate domain:

| Characteristic | Domain | Rationale |
|---|---|---|
| Vectorizable, compute-dense, regular data flow | **AIE** | Maps to SIMD MAC units |
| Bit-level manipulation, irregular control, ultra-low-latency | **PL** | Maps to LUTs/FFs/DSP48 |
| Control-plane, orchestration, slow-rate monitoring | **PS** | ARM Cortex-A72/R5 |
| Standard DSP function with Vitis Library support | **AIE (Library IP)** | Pre-optimized implementation |

---

### Step 2: Compute Analysis

**Question answered:** *"How many AIE tiles are needed to sustain the required throughput?"*

For each AIE-candidate block:

1. **Count MACs per output sample** from the algorithm (e.g., N-tap FIR = N MACs/sample)

2. **Look up tile MAC capacity** for the data-type pair on the target architecture:

   Load architecture reference: [./references/aie-architecture.md](./references/aie-architecture.md), [./references/aie-ml-architecture.md](./references/aie-ml-architecture.md), or [./references/aie-ml-v2-architecture.md](./references/aie-ml-v2-architecture.md)

3. **Look up clock frequency** for the target speed grade:

   Load device reference: [./references/device-catalog.md](./references/device-catalog.md)

4. **Compute tiles required:**

```
throughput_per_tile = MACs_per_cycle × clock_freq        [MACs/s]
required_throughput = sample_rate × MACs_per_sample      [MACs/s]
tiles_compute = ceil(required_throughput / throughput_per_tile) × overhead_factor
```

- **Overhead factor**: 1.2 (accounts for loop control, pipeline fill/drain, non-MAC instructions)
- For **multi-rate** blocks: use the higher of input/output sample rate for the compute-intensive section
- For **decimation filters**: effective compute = taps × input_rate (not output_rate)

#### Compute Example (Farrow Filter):
- 19 MACs/sample, cint16 × int16 on AIE → 16 MACs/cycle, 1 GHz clock
- throughput_per_tile = 16 × 1e9 = 16 GMACs/s
- required_throughput = 1e9 × 19 = 19 GMACs/s
- tiles_compute = ceil(19/16) × 1.2 = ceil(1.19) × 1.2 ≈ 2 tiles

---

### Step 3: Storage Analysis

**Question answered:** *"Does all the data (coefficients, state, I/O buffers) fit in local tile memory?"*

For each AIE-candidate block:

1. **Enumerate stored data per tile:**

| Data Category | Formula | Notes |
|---|---|---|
| Coefficients | num_coefficients × bytes_per_coeff | Halved if symmetric exploitation used |
| State/history | filter_order × bytes_per_sample | Sliding window for FIR, twiddle for FFT |
| I/O buffers (ping-pong) | num_buffers × frame_size × bytes × 2 | Double-buffering for continuous streaming |
| Program code | Variable (typically 2–8 KB) | Counted against 16 KB program memory limit |

2. **Sum total storage per tile**

3. **Compare against available memory:**

| Resource | AIE | AIE-ML / AIE-ML v2 |
|---|---|---|
| Local data memory | 32 KB (8 banks × 4 KB) | 64 KB (8 banks × 8 KB) |
| Accessible total (4 modules) | 128 KB (shared with neighbors) | 256 KB (shared with neighbors) |
| Memory Tiles | — | 512 KB each (separate block) |
| Usable per tile (with 0.75 factor) | ~24 KB | ~48 KB |

   The 0.75 utilization factor accounts for alignment constraints, stack, and DMA descriptors.

4. **Compute tiles for storage:**

```
tiles_storage = ceil(total_required_bytes / usable_memory_per_tile)
```

5. **Coefficient placement decision** (AIE-ML/v2 only):

   Coefficients can reside in **local tile memory** or in **Memory Tiles** (512 KB each). The choice depends on whether the remote streaming bandwidth can satisfy the algorithm's coefficient access rate.

   **Architecture bandwidth comparison:**

   | Storage Location | Bandwidth | Notes |
   |---|---|---|
   | Local tile memory | 200+ GB/s per tile | 256-bit wide, multiple ports, effectively unlimited for coefficient reads |
   | Memory Tile → Compute (stream) | 32 bits × AIE_clock per stream (e.g., 5 GB/s @ 1250 MHz) | Limited — this is the bottleneck |

   **Coefficient access analysis:**

   Determine the algorithm's total coefficient read rate:
   ```
   total_coeff_BW = sample_rate × coefficients_per_output_sample × sizeof_coeff
   ```

   Then determine per-tile demand (divided across N compute tiles):
   ```
   coeff_demand_per_tile = total_coeff_BW / N_tiles
   ```

   **Coefficient reuse pattern:**
   - If coefficients are **reused** across consecutive samples (same filter applied to all inputs): coefficients are loaded once into local memory and reused indefinitely. Memory Tiles are viable (one-time load, negligible ongoing bandwidth).
   - If coefficients are **unique per sample** (e.g., multi-channel filters where each sample belongs to a different channel with its own coefficient set): every sample requires fresh coefficient data at the full rate above.

   **Decision:**
   - If `coeff_demand_per_tile ≤ available stream BW per tile` → Memory Tiles viable. Exclude coefficients from local tile storage budget.
   - If `coeff_demand_per_tile > available stream BW per tile` → Coefficients must be **local**. Include in per-tile storage calculation.

6. **Storage tile count (final):**

   When coefficients must be local:
   ```
   total_storage = total_state_bytes + total_coefficient_bytes
   tiles_storage = ceil(total_storage / usable_memory_per_tile)
   ```

   When coefficients can reside in Memory Tiles:
   ```
   tiles_storage = ceil(total_state_bytes / usable_memory_per_tile)
   memory_tiles  = ceil(total_coefficient_bytes / 512 KB)
   ```

   The `usable_memory_per_tile` includes the 0.75 utilization factor (alignment, stack, DMA overhead). Report this factor and the raw tile memory explicitly in the output.

---

### Step 4: Bandwidth Analysis

**Question answered:** *"Can the hardware interfaces deliver data fast enough to keep the compute tiles fed?"*

For each AIE-candidate block:

1. **Calculate required I/O bandwidth:**
   - Input BW = input_sample_rate × bytes_per_input_sample × num_channels
   - Output BW = output_sample_rate × bytes_per_output_sample × num_channels

2. **Determine PLIO count (PL ↔ AIE interface):**

   All architectures: **64-bit PLIO @ 500 MHz = 4 GB/s per stream** (configurable as 32/64/128-bit physical width)

```
PLIOs_in  = ceil(input_BW / 4 GB/s)
PLIOs_out = ceil(output_BW / 4 GB/s)
PLIOs_total = PLIOs_in + PLIOs_out
```

3. **Check per-column limits:**
   - All architectures: 8 input + 6 output streams per column
   - Per-column aggregate: 32 GB/s PL→AIE, 24 GB/s AIE→PL
   - If PLIOs exceed single-column capacity → design must span multiple columns

4. **Check intra-array stream bandwidth (tile-to-tile inside AIE array):**

| Architecture | Crossbar Width | Clock | BW/stream | Streams per tile |
|---|---|---|---|---|
| AIE | 32-bit | 1 GHz (-1L) | 4 GB/s | 2 in + 2 out |
| AIE-ML | 32-bit | 1 GHz (-1L) | 4 GB/s | 1 in + 1 out |
| AIE-ML v2 | 64-bit | 1 GHz (-1L) | 8 GB/s | 1 in + 1 out |

   Verify that tile-to-tile streaming can sustain the required data rate between cascaded stages.

5. **Memory bandwidth (DMA ↔ tile):**
   - AIE: 2× 256-bit load + 1× 256-bit store per cycle = 96 GB/s per tile
   - AIE-ML/v2: 200+ GB/s per tile
   - Rarely the bottleneck for single-tile designs; relevant for multi-tile shared-memory patterns

#### Bandwidth Example (Farrow Filter):
- Input: 1 Gsps × 4 bytes (cint16) = 4 GB/s → 1 PLIO
- Output: 1 Gsps × 4 bytes = 4 GB/s → 1 PLIO
- Coefficients: streamed at sub-rate → 1 PLIO
- Total: 3 PLIOs — well within single-column limits

---

### Step 5: PL Resource Estimation

**Question answered:** *"How many BRAMs, URAMs, and DSP58s are needed for blocks assigned to PL?"*

Load reference: [./references/pl-resources.md](./references/pl-resources.md)

For each block assigned to PL (data movers, buffers, corner-turns, control logic):

1. **Identify the PL function** (FIFO, ping-pong buffer, corner-turn, coefficient store, data mover, etc.)

2. **Determine access pattern:**
   - Sequential (streaming) → full port packing (multiple samples per 72-bit read)
   - Random/strided (corner-turn, transpose) → 1 sample per cycle per port
   - Parallel (N simultaneous streams) → requires N/2 memory blocks minimum

3. **Compute three constraints:**
   ```
   blocks_for_capacity    = ceil(total_bytes / block_capacity)
   blocks_for_BW          = ceil(required_sample_rate / sample_rate_per_port)
   blocks_for_parallelism = ceil(num_parallel_streams / ports_per_block)
   blocks_needed = max(blocks_for_capacity, blocks_for_BW, blocks_for_parallelism)
   ```

4. **Select BRAM vs URAM:** below ~4 KB use BRAM; above ~4 KB use URAM

5. **Compare against device PL budget** (from [./references/device-catalog.md](./references/device-catalog.md))

---

### Step 6: Partitioning Decision

Combine the four analyses (compute, storage, bandwidth, PL resources) to produce the final recommendation.

#### 6.1 Dominant Constraint Identification

For each AIE block:
```
tiles_required = max(tiles_compute, tiles_storage)
```

| Condition | Classification | Typical Algorithms |
|---|---|---|
| tiles_compute >> tiles_storage | **Compute-bound** | Short filters, element-wise ops, mixers |
| tiles_storage >> tiles_compute | **Storage-bound** | Long FIRs, large FFTs, polyphase filterbanks |
| PLIOs exceed budget | **Bandwidth-bound** | High-rate multi-channel systems |

#### 6.2 Total Resource Check

- Sum `tiles_required` across all AIE blocks
- Compare against target device capacity (from [./references/device-catalog.md](./references/device-catalog.md))
- If total > 80% of device tiles → warn "near capacity, limited room for growth"
- If total > device tiles → flag "exceeds device capacity" and recommend device upgrade

#### 6.3 Domain Assignment

| Block Attribute | Assign To | Rationale |
|---|---|---|
| Vectorizable + maps to MAC table + streaming | **AIE** | SIMD vector processor sweet spot |
| Bit-manipulation, CRC, scrambling, framing | **PL** | LUT-based logic, no MAC needed |
| Ultra-low-latency (<10 cycles) requirement | **PL** | AIE has pipeline latency overhead |
| Control-plane, register config, slow monitoring | **PS** | ARM processors handle software tasks |
| Ambiguous (could go either way) | **Flag for user** | Provide trade-off analysis |

#### 6.4 Cascade and Streaming Topology

- Pipeline stages within AIE connect via **AXI4-Stream** (no PLIO cost — streams stay inside the array)
- Multi-tile filters (CASC_LEN > 1) connect via:
  - **Cascade interface** (384-bit) on AIE — dedicated inter-tile connection
  - **Shared memory** on AIE-ML/v2 — tiles access neighboring memory modules
- Data moving between AIE and PL domains requires PLIOs

#### 6.5 Warnings and Flags

Generate warnings for:
- Total tiles > 80% device capacity
- Compute vs. storage imbalance > 3× (optimization opportunity)
- Data types requiring emulation (e.g., float32 × float32 on AIE-ML → half-rate)
- PLIO utilization > 70% of device budget (routing congestion risk)
- Single block requiring > 50% of device (design may be fragile)

---

### Step 7: Library Matching

For blocks identified as standard DSP functions, recommend Vitis DSP Library IPs.

Load reference: [./references/vitis-dsp-library.md](./references/vitis-dsp-library.md)

| Algorithm Block | Recommended Library IP | Key Parameters to Set |
|---|---|---|
| FIR filter | `fir_sr_asym` / `fir_sr_sym` / `fir_decimate_hb` | TP_FIR_LEN, TP_CASC_LEN, TP_SSR |
| FFT/IFFT | `fft_ifft_dit_1ch` or `vss_fft_ifft_1d` | TP_POINT_SIZE, TP_SSR, TP_CASC_LEN |
| FFT (non-power-of-2) | `mixed_radix_fft` | TP_POINT_SIZE |
| DDS/NCO | `dds_mixer` | TP_MIXER_MODE, TP_SSR |
| Mixer (complex multiply) | `dds_mixer` (mode=2) | TP_SSR |
| FIR (half-band) | `fir_decimate_hb` / `fir_interpolate_hb` | TP_FIR_LEN, TP_SSR |
| Matrix multiply | `matrix_mult` / `matrix_vector_mul` | TP_DIM_A, TP_DIM_B, TP_DIM_AB |
| Multi-channel filter | `fir_tdm` | TP_FIR_LEN, TP_TDM_CHANNELS |
| Windowing | `fft_window` | TP_POINT_SIZE |
| Correlation / matched filter | `conv_corr` | TP_COMPUTE_MODE |

For each recommended IP:
- Suggest initial SSR and CASC_LEN based on throughput requirements
- Note: pair with `config-qor-helper` skill for detailed resource/performance prediction
- Note: pair with `dsp-library-instantiator` skill for code generation

> **FFT/IFFT tile estimation — ABSOLUTE RULE:** Do NOT produce ANY tile count estimate for FFT or IFFT blocks. Do NOT use N·log₂N, do NOT provide "realistic estimates", do NOT give order-of-magnitude guesses. FFT IPs (`vss_fft_ifft_1d`, `fft_ifft_dit_1ch`, `mixed_radix_fft`) are **composite implementations that span both AIE compute tiles and PL (HLS) components**. Their resource usage cannot be derived from first principles. For FFT blocks, report: **"TBD — use `config-qor-helper` for AIE tile count and PL resource usage."**

#### Composite Pipeline Guidance

For multi-block DSP pipelines that combine multiple library IPs:

| Composite Pipeline | Library IPs | Connectivity |
|---|---|---|
| Polyphase channelizer (analysis) | `fir_tdm` → `vss_fft_ifft_1d` | Direct AIE stream (SSR-parallel polyphase outputs feed FFT inputs — no transpose needed) |
| Polyphase channelizer (synthesis) | `vss_fft_ifft_1d` → `fir_tdm` | Direct AIE stream (reverse direction) |
| DDC chain | `dds_mixer` → `fir_decimate_hb` → `fir_decimate_asym` | Cascade within AIE array |
| DUC chain | `fir_interpolate_asym` → `fir_interpolate_hb` → `dds_mixer` | Cascade within AIE array |
| Windowed FFT | `fft_window` → `fft_ifft_dit_1ch` | Direct AIE stream |

---

### Step 8: Output Report

Generate a structured partitioning report with the following sections.

> **Output precision:** Provide a single best estimate per block, not a range. Show the calculation and state assumptions explicitly. If uncertainty exists, give the best estimate with a note on what would change it.

#### 8.1 Block-by-Block Partitioning Table

```
| Block | Domain | Tiles (Compute) | Tiles (Storage) | Tiles (Final) | Dominant Constraint | Rationale |
|-------|--------|-----------------|-----------------|---------------|--------------------:|-----------|
| ...   | AIE    | ...             | ...             | ...           | Compute/Storage     | ...       |
```

#### 8.2 Resource Summary

```
Total AIE tiles required: XX / YY available (ZZ% utilization)
Total PLIOs: XX in + XX out = XX total
PL resources: XX BRAMs, XX URAMs, XX DSP58s
Dominant constraint: [Compute | Storage | Bandwidth]
```

#### 8.3 PLIO Configuration

```
| PLIO | Direction | Data Type | Rate | Width | Connected Block |
|------|-----------|-----------|------|-------|-----------------|
| ...  | in/out    | cint16    | 1 Gsps | 64-bit | FIR stage 1 |
```

#### 8.4 Data Flow Diagram (text-based)

```
[PL: Data Mover] --PLIO--> [AIE: FIR Stage 1] --stream--> [AIE: FIR Stage 2] --PLIO--> [PL: Output]
```

#### 8.5 Recommendations

- Next steps (which skills to invoke): `dsp-library-instantiator`, `create-template-aie`, `config-qor-helper`
- Optimization opportunities (if compute/storage imbalanced)
- Device upgrade path (if near capacity)

#### 8.6 Warnings

List any flags from Step 6.5.

---

## Decision Trees for Ambiguous Cases

### AIE vs. PL Decision

When a block could go either way, present the trade-off:

| Factor | Favors AIE | Favors PL |
|--------|-----------|-----------|
| Data width | ≥16-bit arithmetic | 1–8 bit manipulation |
| Operation regularity | Uniform SIMD pattern | Irregular/conditional |
| Required latency | >100 ns acceptable | <10 ns required |
| Throughput scaling | Scales with tiles (parallel) | Scales with clock + pipelining |
| Power efficiency | Higher for vector math | Higher for bit ops |
| Available resources | Tiles available on device | DSP48/LUT budget available |

### Algorithm Exceeds Device

If total tiles > device capacity:
1. Recommend larger device from same family (e.g., VE2302 → VE2802)
2. Suggest algorithmic simplification (reduce taps, lower precision, exploit symmetry)
3. Identify blocks that could move to PL to free AIE tiles

### Multi-Rate Systems

For systems with rate changes (decimation/interpolation):
1. Track sample rate at each stage boundary
2. Use input rate for compute analysis of decimation stages
3. Use output rate for compute analysis of interpolation stages
4. Propagate rates through the pipeline to size downstream blocks correctly
