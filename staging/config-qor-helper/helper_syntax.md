<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Config QoR Helper Script Syntax

## Command

```bash
python config_qor_helper.py --ip <IP_NAME> --constraints_file <CONSTRAINT_FILE.JSON> --out_csv_file <*.CSV>
```

## Parameters

| Argument | Description |
|----------|-------------|
| `--ip <IP_NAME>` | Any DSP library IP (e.g., `fft_ifft_dit_1ch`) |
| `--constraints_file <path>` | JSON constraint file with design requirements |
| `--out_csv_file <path>` | Output CSV file for predicted configurations |

## Script Location

```
${DSPLIB_ROOT}/L2/meta/scripts/qor_helper/
```

## Path Handling

- `--constraints_file`: Accepts absolute path — no need to copy into `qor_helper/constraints/` directory.
- `--out_csv_file`: Can write to any absolute path. Recommended: `<ABSOLUTE_PATH>/results/`
- Use the same base name for both constraint and output files (e.g., `fft_512_1000.json` → `fft_512_1000.csv`).

## Full Example

```bash
cd ${DSPLIB_ROOT}/L2/meta/scripts/qor_helper
python config_qor_helper.py \
  --ip fft_ifft_dit_1ch \
  --constraints_file /home/user/project/constraints/fft_512_1000.json \
  --out_csv_file /home/user/project/results/fft_512_1000.csv
```
