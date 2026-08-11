<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# PL Resource Estimation Reference

Resource estimation for blocks assigned to Programmable Logic (PL) in Versal devices.
Use this reference when the workload-partition-advisor assigns a function to PL and needs to estimate BRAM, URAM, DSP58, or LUT usage.

Source: AM007 (Versal Adaptive SoC Memory Resources Architecture Manual, v1.2)

---

## Block RAM (BRAM)

| Property | Value |
|---|---|
| Capacity per block | 36 Kb (4,608 bytes including parity) |
| Split mode | Two independent 18 Kb RAMs OR one 36 Kb |
| TDP port widths | 4K×9, 2K×18, 1K×36 |
| SDP port widths | 512×72 (36 Kb) or 512×36 (18 Kb) |
| Port type | True dual-port (TDP): 2 independent read/write ports |
| Cascade | Dedicated routing between adjacent BRAMs (no fabric penalty) |
| ECC | 64-bit error correction per 36 Kb block |
| Column density | ~24 BRAMs per clock region per column |
| Max clock | 500+ MHz (speed-grade dependent) |

## UltraRAM (URAM)

| Property | Value |
|---|---|
| Capacity per block | 288 Kb (36,864 bytes = 36 KB) |
| Configuration | Fixed 4K×72 (4096 addresses × 72 bits) |
| Port type | Single-clock, two-port (internally double-pumped SRAM) |
| Density vs BRAM | 8× capacity per block |
| Cascade | Zero-penalty dedicated routing within column |
| Column density | ~24 URAMs per clock region per column |
| Pipeline stages | Up to 4 per port interface |
| Max clock | 500+ MHz (speed-grade dependent) |

## DSP58 (Versal DSP Slice)

| Property | Value |
|---|---|
| Multiplier | 27 × 24 bits (or 18 × 18 in compat mode) |
| Accumulator | 58-bit |
| Pre-adder | 27-bit |
| Max clock | 500+ MHz (speed-grade dependent) |
| Complex multiply | 3 DSP58s per cint16 × cint16 |
| Real MAC | 1 DSP58 per int16 × int16 MAC |

---

## Bandwidth by Data Type

BRAM and URAM have 72-bit wide ports. The number of samples that fit in one port read depends on the data type.

### Sequential Access (streaming FIFOs, ping-pong buffers)

Full port utilization — multiple samples packed per read.

| Data Type | Width (bits) | Samples per 72-bit read | Max sample rate per port @ 500 MHz |
|---|---|---|---|
| int16 | 16 | 4 | 2.0 Gsps |
| cint16 | 32 | 2 | 1.0 Gsps |
| int32 | 32 | 2 | 1.0 Gsps |
| cint32 | 64 | 1 | 500 Msps |
| float32 | 32 | 2 | 1.0 Gsps |
| cfloat32 | 64 | 1 | 500 Msps |

Formula:
```
samples_per_read = floor(72 / sample_width_bits)
sample_rate_per_port = samples_per_read × PL_clock
```

### Random/Strided Access (corner-turn, transpose, channel-interleaved reads)

Only 1 addressable word per cycle per port, regardless of port width.

```
sample_rate_per_port = PL_clock    (e.g., 500 Msps at 500 MHz)
```

This applies when each successive read targets a different address (non-sequential access pattern).

### Parallel Streams (N channels read simultaneously)

Each independent stream requires its own memory port:
- BRAM (TDP): 2 independent ports → serves 2 simultaneous streams
- BRAM (SDP): 1 dedicated read port + 1 dedicated write port → 1 read stream + 1 write stream
- URAM: 2 ports → serves 2 simultaneous streams

```
blocks_for_parallelism = ceil(num_parallel_streams / ports_per_block)
```

---

## Combined Resource Estimation

For any PL memory function, compute three constraints and take the maximum:

```
blocks_for_capacity    = ceil(total_bytes / block_capacity)
blocks_for_BW          = ceil(required_sample_rate / sample_rate_per_port)
blocks_for_parallelism = ceil(num_parallel_streams / ports_per_block)

blocks_needed = max(blocks_for_capacity, blocks_for_BW, blocks_for_parallelism)
```

Where:
- `block_capacity` = 4,608 bytes (BRAM) or 36,864 bytes (URAM)
- `sample_rate_per_port` = from bandwidth tables above (depends on access pattern + data type)
- `ports_per_block` = 2 (BRAM TDP or URAM)

---

## Estimation Formulas for Common PL Functions

| PL Function | Primary Resource | Capacity Formula | Bandwidth Constraint |
|---|---|---|---|
| Ping-pong buffer | BRAM or URAM | `ceil(frame_bytes × 2 / block_cap)` | Sequential: use BW table |
| Deep FIFO (>4 KB) | URAM | `ceil(depth × width_bytes / 36864)` | Sequential: use BW table |
| Shallow FIFO (≤4 KB) | BRAM | `ceil(depth × width_bytes / 4608)` | Sequential: use BW table |
| Coefficient store | URAM | `ceil(total_coeff_bytes / 36864)` | Random access: 500 Msps/port |
| Corner-turn buffer | URAM | `ceil(N_ch × frame_size × bytes / 36864)` | Strided: 500 Msps/port |
| Data mover (HLS) | BRAM | 2–4 BRAMs typical | N/A |

---

## BRAM vs URAM Selection

| Criterion | Use BRAM | Use URAM |
|---|---|---|
| Buffer size | < 4 KB | ≥ 4 KB |
| Access pattern | Wide (need ECC, byte-write-enable) | Deep (large sequential storage) |
| Port flexibility | Need independent port widths | Fixed 72-bit is acceptable |
| Area efficiency | Small count (< 4 blocks) | Large count (URAM is 8× denser) |
| Cascading | Short chains | Long chains (zero-penalty column cascade) |

**Break-even rule of thumb:** below ~4 KB use BRAM; above ~4 KB use URAM for better density.

---

## Worked Examples

### Example 1: Streaming FIFO for cint16 @ 983.04 Msps

- Access pattern: sequential
- Data type: cint16 (32 bits = 4 bytes)
- FIFO depth: 4096 samples
- Capacity: 4096 × 4 = 16,384 bytes → `ceil(16384 / 36864)` = 1 URAM
- BW: sequential cint16 → 1.0 Gsps/port @ 500 MHz → 1 port handles 983 Msps ✓
- Parallelism: 1 read + 1 write = 2 ports needed → 1 URAM (has 2 ports) ✓
- **Result: 1 URAM**

### Example 2: Corner-turn for 64-channel cint32 @ 491.52 Msps, 4096 samples/frame

- Access pattern: strided (write sequential per channel, read across channels)
- Data type: cint32 (64 bits = 8 bytes)
- Total storage: 64 × 4096 × 8 = 2,097,152 bytes
- Capacity: `ceil(2097152 / 36864)` = 57 URAMs
- BW: strided access → 500 Msps/port; need 491.52 Msps → 1 port handles it ✓
- Parallelism: if reading all 64 channels in 1 cycle → `ceil(64 / 2)` = 32 URAMs
- **Result: max(57, 1, 32) = 57 URAMs (capacity-dominated)**

### Example 3: Ping-pong buffer for int16 @ 1.5 Gsps, 256-sample frames

- Access pattern: sequential
- Data type: int16 (16 bits = 2 bytes)
- Capacity: 256 × 2 × 2 (ping-pong) = 1024 bytes → `ceil(1024 / 4608)` = 1 BRAM
- BW: sequential int16 → 2.0 Gsps/port @ 500 MHz → 1 port handles 1.5 Gsps ✓
- Parallelism: 1 read + 1 write → 1 BRAM (TDP has 2 ports) ✓
- **Result: 1 BRAM**

### Example 4: Coefficient store for 256 channels × 36 taps × cint16

- Access pattern: random (different channel each cycle)
- Data type: cint16 (4 bytes)
- Total storage: 256 × 36 × 4 = 36,864 bytes
- Capacity: `ceil(36864 / 36864)` = 1 URAM
- BW: random access → 500 Msps/port; need coefficients at channel rate
- **Result: 1 URAM (if channel rate ≤ 500 Msps)**
