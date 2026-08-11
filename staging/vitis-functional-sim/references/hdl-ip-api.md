<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# HDL IP API Reference

All HDL IPs follow the same lifecycle pattern:

```
1. getDefaultConfig() → get default configuration object
2. Customize config fields
3. Instantiate IP with config
4. Create Control object for per-run parameters
5. Call run(input_data, control) → output + status
```

---

## xFFT (Versal FFT v9.1)

Supports fixed-point and floating-point modes. Architectures 1–4 (Radix-4/2 burst, pipelined streaming, lite).

### Configuration

```python
from vfs.xfft import xfft

config = xfft.getDefaultConfig()
config.c_nfft_max = 10              # log2(max FFT size), e.g. 10 → 1024-point
config.c_arch = 3                   # 1=Radix-4, 2=Radix-2, 3=Pipelined, 4=Lite
config.c_use_flt_pt = 1            # 0=fixed-point, 1=single-precision float
config.c_input_width = 32          # Input data width (bits)
config.c_twiddle_width = 32        # Twiddle factor width
config.c_has_scaling = 1           # Enable scaling schedule
config.c_has_bfp = 1               # Block floating-point
config.c_nssr = 1                  # Super sample rate factor
config.c_has_rounding = 0          # Rounding mode
config.c_has_nfft = 0              # 0=fixed size, 1=runtime configurable size

fft_model = xfft(config)
```

### Control & Execution

```python
import varray as va
import numpy as np

# Prepare complex input
signal = np.cos(2 * np.pi * 30 * np.arange(1024) / 1024)
data_in = va.array(signal + 0j, va.cdouble)

# Run forward FFT
ctrl = xfft.Control(nfft=10, direction=1)  # 1=forward, 0=inverse
output, block_exp, overflow = fft_model.run(data_in, ctrl)

result = np.asarray(output, dtype=np.complex128)
```

### MATLAB Example

```matlab
config = vfs.xfft.getDefaultConfig();
config.c_nfft_max = 10;
config.c_arch = 3;
config.c_use_flt_pt = 1;
config.c_input_width = 32;
config.c_twiddle_width = 32;
config.c_has_scaling = 1;
config.c_has_bfp = 1;

fft_model = vfs.xfft(config);

% Generate signal
N = 1024;
signal = cos(2*pi*30*(0:N-1)/N);
data_in = varray.cdouble(complex(signal, zeros(1, N)));

% Run
ctrl = vfs.xfft.Control('nfft', 10, 'direction', 1);
[output, block_exp, overflow] = fft_model.run(data_in, ctrl);

result = double(output);
fprintf('FFT output: %d points\n', length(result));
```

### Key Config Fields

| Field | Default | Description |
|-------|---------|-------------|
| `c_nfft_max` | 10 | log2(max FFT size) |
| `c_arch` | 1 | Architecture: 1=Radix-4 burst, 2=Radix-2 burst, 3=Pipelined streaming, 4=Lite |
| `c_use_flt_pt` | 0 | 0=fixed-point, 1=floating-point |
| `c_input_width` | 16 | Input word width (bits) |
| `c_twiddle_width` | 16 | Twiddle factor width |
| `c_has_scaling` | 1 | Enable scaling |
| `c_has_nfft` | 0 | Runtime-configurable FFT size |

---

## vrfFFT (VRF FFT v1.2)

Fixed-point FFT, 8–4096 points. Supports scaled and unscaled modes.

### Configuration

```python
from vfs.vrfFFT import vrfFFT

config = vrfFFT.getDefaultConfig()
config.data_width_in = 16           # Input width: 16 or 18 bits
config.data_width_out = 16          # Output width: 16, 18, or 32 (unscaled)

fft = vrfFFT(config)
```

### Control & Execution

```python
import varray as va
import numpy as np

NFFT = 1024
SCALING = 1.0 / NFFT

# Generate complex input (fixed-point range [-1, 1))
signal = np.cos(2 * np.pi * 64 * np.arange(NFFT) / NFFT)
scale = 2 ** (16 - 1)
signal_q = np.round(signal * scale / 2) / scale
data_in = va.array(signal_q + 0j, va.cdouble)

# Control
ctrl = vrfFFT.Control(
    scaling_factor=SCALING,
    direction=1,              # 1=forward, 0=inverse
    point_size=int(np.log2(NFFT)),  # log2(N)
    reorder_output=1          # 1=natural order, 0=bit-reversed
)

# Run
output, overflow = fft.run(data_in, ctrl)
result = np.asarray(output, dtype=np.complex128)
print(f"Overflow: {np.any(overflow)}")
```

### MATLAB Example

```matlab
config = vfs.vrfFFT.getDefaultConfig();
config.data_width_in = 16;
config.data_width_out = 16;
fft_model = vfs.vrfFFT(config);

NFFT = 1024;
t = (0:NFFT-1).';
signal = cos(2*pi*64*t/NFFT);
in_scale = 2^(16-1);
signal_q = round(signal * in_scale / 2) / in_scale;
data_in = varray.cdouble(complex(signal_q, zeros(NFFT, 1)));

ctrl = vfs.vrfFFT.Control('scaling_factor', 1/NFFT, ...
    'direction', 1, 'point_size', log2(NFFT), 'reorder_output', 1);
[output, overflow] = fft_model.run(data_in, ctrl);

fprintf('vrfFFT: %d points, overflow=%d\n', length(output), any(overflow));
```

### Batch & Partial Frame Behavior

- Input > N points: auto-processes as multiple N-point FFTs
- Input < N points: buffered internally, output empty until N samples accumulated
- Stateful: maintains internal buffer across `run()` calls

---

## vrfChannelizer (VRF Channelizer v1.2)

Multi-channel polyphase filter bank with 7 operating modes.

### Configuration

```python
from vfs.vrfChannelizer import vrfChannelizer

config = vrfChannelizer.getDefaultConfig()
config.mode = 0                    # 0=Rx, 1=Tx, 2=Filter, 3=OS-Rx, 4=OS-Tx, 5=SSR-Tx, 6=SSR-Rx
config.fir_max_asym_len = 256      # Max FIR filter length

chan = vrfChannelizer(config)
```

### Control & Execution

```python
import varray as va
import numpy as np

# Create control for 16-channel, 512 samples/channel
control = chan.createControl(num_channels=16, num_samples_per_channel=512)
control.fft_scaling = 0.5
control.fir_coeff = my_filter_coefficients  # numpy array

# Input: complex double
data_in = va.array(input_signal + 0j, va.cdouble)

# Run → returns overflow status
overflow_status = chan.run(data_in, control)
```

### Operating Modes

| Mode | Name | Description |
|------|------|-------------|
| 0 | Standard Rx | Channelize wideband → narrowband channels |
| 1 | Standard Tx | Synthesize narrowband channels → wideband |
| 2 | Filter Only | Polyphase FIR without FFT |
| 3 | Oversampled Rx | Rx with oversampled subbands |
| 4 | Oversampled Tx | Tx with oversampled subbands |
| 5 | SSR Tx | Super Sample Rate transmit |
| 6 | SSR Rx | Super Sample Rate receive |

---

## firCompiler (FIR Compiler v7.2)

Multi-tap, multi-channel FIR filter. Maintains persistent state across calls (streaming mode).

### Configuration

```python
from vfs import firCompiler

config = firCompiler.Config(
    coeff=list(coefficients),     # Filter coefficients (list of floats)
    num_coeffs=128,               # Number of taps
    coeff_width=16,               # Coefficient word length (bits)
    coeff_fract_width=15,         # Coefficient fraction length
    data_width=16,                # Data word length
    data_fract_width=14,          # Data fraction length
)

fir = firCompiler(config)
```

### Execution

```python
import varray as va
import numpy as np
from scipy.signal import firwin, lfilter

# Design filter
coeff = firwin(128, 0.25)  # 128-tap lowpass, cutoff=0.25

# VFS FIR
fir_hw = firCompiler(firCompiler.Config(
    coeff=list(coeff),
    num_coeffs=128,
    coeff_width=16,
    coeff_fract_width=15,
    data_width=16,
    data_fract_width=14
))

# Test signal
x = np.random.randn(1024)

# Run VFS
y_hw = np.asarray(fir_hw.run(va.array(x, va.double))).flatten()

# Compare with scipy reference
y_ref = lfilter(coeff, 1.0, x)
max_err = np.max(np.abs(y_ref - y_hw))
print(f"Max error: {max_err:.4e}")
assert max_err < 1e-2, f"FAIL: error {max_err} exceeds tolerance"
```

### MATLAB Example

```matlab
%% FIR Compiler: VFS vs MATLAB filter()
num_taps = 128;
coeff = fir1(num_taps - 1, 0.25);  % 128-tap lowpass

fir_hw = vfs.firCompiler(vfs.firCompiler.Config( ...
    'coeff', coeff, ...
    'num_coeffs', num_taps, ...
    'coeff_width', 16, ...
    'coeff_fract_width', 15, ...
    'data_width', 16, ...
    'data_fract_width', 14));

% Test signal
x = randn(1, 1024);

% VFS
y_hw = double(fir_hw.run(varray.double(x)));
y_hw = y_hw(:).';

% Reference
y_ref = filter(coeff, 1.0, x);

% Compare
max_err = max(abs(y_ref - y_hw));
fprintf('Max error: %.4e\n', max_err);
assert(max_err < 1e-2, sprintf('FAIL: error %.4e exceeds tolerance', max_err));
fprintf('PASS\n');
```

### Key Properties

- **Stateful**: Filter state persists across `run()` calls (streaming mode)
- **Call `reset()`** between independent test vectors to clear state
- **Multi-channel**: Supports up to 64 channels with TDM patterns
- **Filter types**: Single-rate, interpolation, decimation, Hilbert transform

---

## vrfADC (VRF Data Converter: ADC)

Converts real analog signals to complex baseband. 4 RF tiles × 2 bands per tile.

### Configuration

```python
from vfs.vrfADC import vrfADC

config = vrfADC.getDefaultConfig()
# Configure tile type: "quad" (4×8 GSPS) or "single" (1×32 GSPS)
config.tile_type = "quad"
config.num_tiles = 4
config.bands_per_tile = 2

adc = vrfADC(config)
```

### Execution

```python
# Input: real analog signal
analog_in = va.array(np.cos(2 * np.pi * 1e9 * t), va.double)

# Output: complex baseband per tile/band
baseband_out = adc.run(analog_in)
```

---

## vrfDAC (VRF Data Converter: DAC)

Converts complex baseband to real analog. Same tile structure as ADC.

### Configuration

```python
from vfs.vrfDAC import vrfDAC

config = vrfDAC.getDefaultConfig()
config.tile_type = "quad"
config.num_tiles = 4
config.bands_per_tile = 2

dac = vrfDAC(config)
```

### Execution

```python
# Input: complex baseband
baseband_in = va.array(complex_signal, va.cdouble)

# Output: real analog signal
analog_out = dac.run(baseband_in)
```

---

## Complete Python Example: vrfFFT vs NumPy Reference

```python
"""VFS functional verification: vrfFFT compared against NumPy FFT"""
from vfs.vrfFFT import vrfFFT
import varray as va
import numpy as np

# --- Configuration ---
NFFT = 1024
DATA_WIDTH_IN = 16
DATA_WIDTH_OUT = 16
SCALING = 1.0 / NFFT

# --- Generate test signal: 2 tones ---
t = np.arange(NFFT)
tone1 = np.cos(2 * np.pi * 64 * t / NFFT)
tone2 = 0.5 * np.cos(2 * np.pi * 200 * t / NFFT)
signal = tone1 + tone2

# Quantize to fixed-point range
in_scale = 2 ** (DATA_WIDTH_IN - 1)
signal_q = np.round(signal * in_scale / 2) / in_scale
signal_q = np.clip(signal_q, -1.0, 1.0 - 1.0 / in_scale)

# --- VFS vrfFFT ---
config = vrfFFT.getDefaultConfig()
config.data_width_in = DATA_WIDTH_IN
config.data_width_out = DATA_WIDTH_OUT
fft_model = vrfFFT(config)

data_in = va.array(signal_q + 0j, va.cdouble)
ctrl = vrfFFT.Control(
    scaling_factor=SCALING,
    direction=1,
    point_size=int(np.log2(NFFT)),
    reorder_output=1
)
fft_out, overflow = fft_model.run(data_in, ctrl)
result = np.asarray(fft_out, dtype=np.complex128)

# --- NumPy Reference ---
ref = np.fft.fft(signal_q) / NFFT
# Quantize reference to match output precision
out_scale = 2 ** (DATA_WIDTH_OUT - 1)
ref_q = (np.round(ref.real * out_scale) + 1j * np.round(ref.imag * out_scale)) / out_scale

# --- Compare ---
error = result - ref_q
max_err = np.max(np.abs(error))
lsb = 1.0 / 2 ** (DATA_WIDTH_OUT - 1)
max_err_lsb = max_err / lsb

print(f"Max error: {max_err:.6e} ({max_err_lsb:.1f} LSBs)")
print(f"Overflow: {np.any(overflow)}")
assert max_err_lsb <= 1.0, f"FAIL: {max_err_lsb:.1f} LSBs exceeds 1.0"
print("PASS")
```

## Complete MATLAB Example: vrfFFT

```matlab
%% VFS functional verification: vrfFFT vs MATLAB fft()
NFFT = 1024;
DATA_WIDTH_IN = 16;
DATA_WIDTH_OUT = 16;
SCALING = 1/NFFT;

% Generate signal: 2 tones
t = (0:NFFT-1).';
tone1 = cos(2*pi*64*t/NFFT);
tone2 = 0.5 * cos(2*pi*200*t/NFFT);
signal = tone1 + tone2;

% Quantize
in_scale = 2^(DATA_WIDTH_IN - 1);
signal_q = round(signal * in_scale / 2) / in_scale;
signal_q = max(min(signal_q, 1.0 - 1.0/in_scale), -1.0);

% Configure vrfFFT
config = vfs.vrfFFT.getDefaultConfig();
config.data_width_in = DATA_WIDTH_IN;
config.data_width_out = DATA_WIDTH_OUT;
fft_model = vfs.vrfFFT(config);

% Run
data_in = varray.cdouble(complex(signal_q, zeros(NFFT, 1)));
ctrl = vfs.vrfFFT.Control('scaling_factor', SCALING, ...
    'direction', 1, 'point_size', log2(NFFT), 'reorder_output', 1);
[fft_out, overflow] = fft_model.run(data_in, ctrl);

% Reference
ref = fft(signal_q) / NFFT;
out_scale = 2^(DATA_WIDTH_OUT - 1);
ref_q = (round(real(ref)*out_scale) + 1j*round(imag(ref)*out_scale)) / out_scale;

% Compare
result = double(fft_out);
err = result - ref_q;
max_err = max(abs(err));
lsb = 1.0 / out_scale;
max_err_lsb = max_err / lsb;

fprintf('Max error: %.1f LSBs, Overflow: %d\n', max_err_lsb, any(overflow));
assert(max_err_lsb <= 1.0, sprintf('FAIL: %.1f LSBs', max_err_lsb));
fprintf('PASS\n');
```

---

## General Notes

- All HDL IPs are **stateful** — they maintain internal buffers across `run()` calls
- Call `reset()` between independent test vectors if you don't want state carryover
- **Batch processing**: input larger than the configured point size auto-segments into multiple frames
- **Partial frames**: input smaller than point size is buffered; output is empty until enough data arrives
- **Overflow detection**: FFT IPs return an overflow flag — always check it
- HDL IPs accept `va.cdouble` (complex double) as input and return the same
