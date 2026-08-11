<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis DSP Library Reference

Standard DSP functions available as pre-optimized AIE implementations in the Vitis DSP Library.
When the workload-partition-advisor identifies a standard DSP function, recommend the corresponding library IP.

## Library IP Catalog

### FIR Filters

| Library IP | Description | Key Parameters |
|---|---|---|
| `fir_sr_asym` | Single-rate asymmetric FIR | TP_FIR_LEN, TP_CASC_LEN, TP_SSR, TP_API (0=window, 1=stream) |
| `fir_sr_sym` | Single-rate symmetric FIR | TP_FIR_LEN, TP_CASC_LEN, TP_SSR |
| `fir_decimate_asym` | Decimation FIR (asymmetric) | TP_FIR_LEN, TP_DECIMATE_FACTOR, TP_CASC_LEN, TP_SSR |
| `fir_decimate_sym` | Decimation FIR (symmetric) | TP_FIR_LEN, TP_DECIMATE_FACTOR, TP_CASC_LEN, TP_SSR |
| `fir_decimate_hb` | Half-band decimation FIR | TP_FIR_LEN, TP_CASC_LEN, TP_SSR |
| `fir_interpolate_asym` | Interpolation FIR (asymmetric) | TP_FIR_LEN, TP_INTERPOLATE_FACTOR, TP_CASC_LEN, TP_SSR |
| `fir_interpolate_hb` | Half-band interpolation FIR | TP_FIR_LEN, TP_CASC_LEN, TP_SSR |
| `fir_interpolate_fract_asym` | Fractional interpolation FIR | TP_FIR_LEN, TP_INTERPOLATE_FACTOR, TP_DECIMATE_FACTOR, TP_CASC_LEN |
| `fir_tdm` | Time-division multiplexed FIR | TP_FIR_LEN, TP_TDM_CHANNELS, TP_CASC_LEN |
| `fir_resampler` | Fractional-rate FIR resampler | TP_FIR_LEN, TP_INTERPOLATE_FACTOR, TP_DECIMATE_FACTOR |

### FFT/IFFT

| Library IP | Description | Key Parameters |
|---|---|---|
| `fft_ifft_dit_1ch` | Single-channel radix-2 DIT FFT/IFFT | TP_POINT_SIZE, TP_FFT_NIFFT, TP_CASC_LEN, TP_SSR |
| `vss_fft_ifft_1d` | Variable-SSR FFT/IFFT (2D decomposition). **Composite: AIE + PL (HLS)** — uses both AIE compute tiles and PL/HLS data movers. Resource estimation requires `config-qor-helper`. | TP_POINT_SIZE, TP_FFT_NIFFT, TP_SSR |
| `mixed_radix_fft` | Mixed-radix FFT (non-power-of-2) | TP_POINT_SIZE, TP_FFT_NIFFT, TP_DYN_PT_SIZE |
| `dft` | General DFT (arbitrary point sizes) | TP_POINT_SIZE, TP_FFT_NIFFT, TP_CASC_LEN |
| `fft_ifft_2d` | 2D FFT/IFFT | TP_POINT_SIZE, TP_FFT_NIFFT, TP_CASC_LEN, TP_SSR |
| `fft_dit_2ch_real` | 2-channel real FFT (packs two real signals) | TP_POINT_SIZE, TP_FFT_NIFFT, TP_CASC_LEN |
| `fft_window` | Windowing function (applied before FFT) | TP_POINT_SIZE, TP_WINDOW_VSIZE, TP_DYN_PT_SIZE |

**FFT IP selection (high-level guidance):**
- `fft_ifft_dit_1ch`: Standard radix-2 DIT, power-of-2 point sizes
- `vss_fft_ifft_1d`: Larger point sizes and SSR
- `mixed_radix_fft`: Non-power-of-2 point sizes
- `dft`: Small arbitrary-size DFT
- `fft_ifft_2d`: 2D transforms (image processing, radar)
- `fft_dit_2ch_real`: Two real-valued signals packed into one complex FFT
- `fft_window`: Apply windowing (Hann, Hamming, etc.) to frames before FFT

**FFT sizing rules:**
- TP_POINT_SIZE: 16 to 65536 (power of 2 for DIT; flexible for mixed_radix/dft)
- TP_SSR: Super-sample rate — increases throughput by using more tiles
- TP_CASC_LEN: Cascade length — distributes stages across tiles
- Tiles used ≈ TP_SSR × TP_CASC_LEN (minimum, actual may be higher)

> **WARNING — FFT tile estimation:** Do NOT produce ANY tile count estimate for FFT/IFFT. These IPs are composite implementations (AIE + PL/HLS) whose resource usage cannot be derived from algorithm complexity. Use `config-qor-helper` skill for precise AIE tile count and PL resource usage.

### DDS and Mixer

| Library IP | Description | Key Parameters |
|---|---|---|
| `dds_mixer` | DDS + complex mixer | TP_MIXER_MODE (0=DDS only, 1=DDS+mixer, 2=mixer only), TP_SSR |
| `dds_mixer_lut` | LUT-based DDS + mixer (alternative implementation) | TP_MIXER_MODE, TP_SSR |

**Mixer modes:**
- Mode 0: DDS only — generates complex sinusoid
- Mode 1: DDS + mixer — generates sinusoid and multiplies with input
- Mode 2: Mixer only — complex multiply of two inputs

### Matrix and Linear Algebra

| Library IP | Description | Key Parameters |
|---|---|---|
| `matrix_mult` | Matrix-matrix multiply | TP_DIM_A, TP_DIM_B, TP_DIM_AB, TP_CASC_LEN |
| `matrix_vector_mul` | Matrix-vector multiply | TP_DIM_A, TP_DIM_B, TP_CASC_LEN |
| `outer_tensor` | Outer tensor product (vector⊗vector) | TP_DIM_A, TP_DIM_B, TP_NUM_FRAMES |
| `kronecker` | Kronecker product | TP_DIM_A, TP_DIM_B, TP_SSR |
| `hadamard` | Hadamard transform | TP_DIM_A, TP_DIM_B, TP_SSR |
| `euclidean_distance` | Euclidean distance calculation | TP_DIM, TP_API, TP_IS_OUTPUT_SQUARED |

### Signal Processing

| Library IP | Description | Key Parameters |
|---|---|---|
| `conv_corr` | Convolution and correlation | TP_COMPUTE_MODE (0=conv, 1=corr), TP_CASC_LEN |
| `sample_delay` | Vectorized delay line | TP_MAX_DELAY, TP_WINDOW_VSIZE, TP_API |
| `cumsum` | Cumulative sum | TP_DIM_A, TP_MODE |
| `func_approx` | LUT-based function approximation (sin, cos, sqrt, etc.) | TP_FUNCTION, TP_INPUT_WINDOW_VSIZE |
| `bitonic_sort` | Bitonic sorting network | TP_ASCENDING, TP_CASC_LEN, TP_SSR |

### Widget Utilities

| Library IP | Description | Use Case |
|---|---|---|
| `widget_real2complex` | Combine real streams to complex | Interface adaptation |
| `widget_api_cast` | Convert between window and stream API | Connecting stream↔window IPs |
| `widget_2ch_real_fft` | Widget for 2-channel real FFT I/O | Interface for `fft_dit_2ch_real` |

### Infrastructure

| Library IP | Description | Key Parameters |
|---|---|---|
| `pkt_switch` | Packet switch — routes packet streams to/from wrapped DSP IPs | Number of inputs, outputs, wrapped IP |

---

## Algorithm-to-Library Mapping

When the algorithm decomposition identifies these patterns, recommend the corresponding library IP.
Each entry maps a single algorithm pattern to a single library IP (1:1 mapping only).

| Algorithm Pattern | Recommended IP | Notes |
|---|---|---|
| Convolution / FIR filter | `fir_sr_asym` or `fir_sr_sym` | Use `_sym` if coefficients are symmetric |
| Decimation filter | `fir_decimate_asym` / `fir_decimate_hb` | Use half-band for 2× decimation |
| Interpolation filter | `fir_interpolate_asym` / `fir_interpolate_hb` | Use half-band for 2× interpolation |
| Fractional resampling | `fir_resampler` | Combined interpolation + decimation |
| FFT / IFFT (power-of-2) | `fft_ifft_dit_1ch` or `vss_fft_ifft_1d` | Use `config-qor-helper` for tile estimate |
| FFT (non-power-of-2) | `mixed_radix_fft` | Flexible point sizes |
| Small DFT (arbitrary size) | `dft` | For small transforms |
| 2D FFT | `fft_ifft_2d` | Image/radar processing |
| Windowing before FFT | `fft_window` | Hann, Hamming, Blackman, etc. |
| Frequency shift / NCO | `dds_mixer` (mode 1) | Or mode 0 for tone generation |
| Complex multiply | `dds_mixer` (mode 2) | Efficient single-tile complex multiply |
| Matrix-matrix multiply | `matrix_mult` | MIMO precoding, beamforming |
| Matrix-vector multiply | `matrix_vector_mul` | Beamforming, linear transform |
| Outer product | `outer_tensor` | Rank-1 updates, correlation matrices |
| Multi-channel filter (same coeffs) | `fir_tdm` | Time-division multiplexing |
| Convolution / cross-correlation | `conv_corr` | Matched filtering, detection |
| Fixed delay / alignment | `sample_delay` | Stream alignment between paths |
| Running sum / integration | `cumsum` | Accumulation, CIC-like operations |
| Nonlinear function (sin, sqrt, ...) | `func_approx` | LUT-based approximation |
| Sorting | `bitonic_sort` | Parallel sorting network |
| Distance metric | `euclidean_distance` | Classification, clustering |
| Packet stream multiplexing | `pkt_switch` | Multi-stream routing to shared IP |

---

## Parameter Selection Guidelines

### SSR (Super Sample Rate)

SSR determines how many samples are processed per clock cycle. Set SSR to meet throughput:

```
required_SSR = ceil(sample_rate / clock_freq)
```

Example: 2 Gsps input on AIE-ML at 1 GHz → SSR = 2

Higher SSR uses more tiles but achieves higher throughput. SSR must be a power of 2.

### CASC_LEN (Cascade Length)

CASC_LEN distributes a single filter across multiple tiles connected in cascade:

**For FIR filters:**
```
min_CASC_LEN = ceil(TP_FIR_LEN / max_taps_per_tile)
```

Where `max_taps_per_tile` depends on data type and memory:
- int16 × int16: ~256 taps/tile (limited by 32 KB AIE or 64 KB AIE-ML memory)
- cint16 × int16: ~128 taps/tile
- cint16 × cint16: ~64 taps/tile

Increasing CASC_LEN beyond minimum reduces compute load per tile (useful when tiles are compute-bound).

**For FFT:**
CASC_LEN distributes FFT stages across tiles. Larger CASC_LEN lowers per-tile compute at cost of latency.

### TP_API (Interface Mode)

- `TP_API = 0` (window): Frame-based processing using ping-pong buffers in memory
- `TP_API = 1` (stream): Sample-by-sample streaming via AXI4-Stream

Use stream API for:
- Continuous high-throughput processing
- When downstream blocks also use streaming

Use window API for:
- Block processing (e.g., FFT needs full frame before processing)
- When data is DMA'd from memory tiles

---

## Tile Estimation for Library IPs

Rough tile estimates for common configurations:

| IP | Configuration | Approximate Tiles |
|---|---|---|
| `fir_sr_asym` (64 taps, SSR=1) | int16×int16, CASC_LEN=1 | 1 |
| `fir_sr_asym` (256 taps, SSR=1) | cint16×int16, CASC_LEN=2 | 2 |
| `fir_sr_asym` (1024 taps, SSR=1) | cint16×int16, CASC_LEN=8 | 8 |
| `fir_tdm` (36 taps, 64 ch, SSR=1) | cint16×int16, CASC_LEN=1 | 1 |
| `fir_tdm` (36 taps, 64 ch, SSR=4) | cint16×int16, CASC_LEN=1 | 4 |
| `dds_mixer` (mode 1, SSR=1) | cint16 | 1 |
| `dds_mixer` (mode 1, SSR=4) | cint16 | 4 |
| `matrix_vector_mul` (16×16) | cint16, CASC_LEN=1 | 1 |

> **WARNING — FFT tile estimation:** Do NOT estimate FFT/IFFT tiles from N·log₂N. Use `config-qor-helper` skill for FFT tile count and throughput. The table below is for rough order-of-magnitude only:

| FFT IP | Configuration | Order-of-magnitude Tiles |
|---|---|---|
| `fft_ifft_dit_1ch` (1024-pt, SSR=1) | cint16, CASC_LEN=2 | ~2–4 |
| `fft_ifft_dit_1ch` (4096-pt, SSR=4) | cint16 | ~16–24 |
| `vss_fft_ifft_1d` (4096-pt, SSR=4) | cint16 | Use `config-qor-helper` |

For precise estimates, use the `config-qor-helper` skill.

---

## Blocks NOT in Vitis DSP Library (implement in PL or custom AIE)

| Function | Recommendation | Rationale |
|---|---|---|
| CRC computation | PL (LUTs) | Bit-level XOR operations |
| Scrambling / descrambling | PL (LUTs/FFs) | Bit manipulation with LFSR |
| Frame synchronization | PL (correlator + FSM) | Irregular control + bit matching |
| JESD204B/C framing | PL (hard IP or logic) | Protocol-specific framing |
| Packet routing / arbitration | PL (AXI interconnect) | Control-plane multiplexing |
| NCO with fine phase control | PL (DSP48) or AIE (DDS) | Depends on SFDR requirements |
| Data movers / DMA | PL (HLS kernel) | Memory-mapped to stream conversion |
| Corner-turn / transpose | PL (URAM buffer) | Large memory + strided access pattern |
| Register configuration | PS (ARM) | Software control plane |
| Runtime reconfiguration | PS (ARM) | Dynamic parameter updates |
