<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Headless Vitis Execution v0.1

Vitis execution is conditional. A direct RTL design with no PS application or
Vitis accelerator remains a Vivado-only flow.

## Command ownership

| Plan section | Agent owner | Runner command |
|---|---|---|
| `acceleration.compile[]`, mode `hls` | `vitis_hls_engineer` | `v++ --compile --mode hls` |
| `acceleration.compile[]`, mode `aie` | `vitis_aie_engineer` | `v++ --compile --mode aie` |
| `acceleration.link` | `amd_soc_platform_integrator` | `v++ --link` |
| `acceleration.package` | `amd_soc_platform_integrator` | `v++ --package` |
| `embedded` | `vitis_sw_engineer` | `vitis -s <generated.py>` |
| Plan aggregation and dispatch | `amd_soc_platform_integrator`; `amd_soc_orchestrator` dispatches | `python3 scripts/v0_1_runner.py vitis --run <run>` |

Agent prompts document ownership and gates. Exact argv construction is
centralized in `scripts/vitis_runner.py`; agents cannot supply arbitrary shell
commands or extra arguments.

The table assigns ownership of plan fields and failure routing. The
deterministic Vitis runner is the sole writer of `vitis-result.json`,
`vitis/commands.json`, generated Python, logs, and generated ELF/XO/libadf,
linked, and packaged outputs. Specialists inspect those results but do not
rewrite them.

## Artifacts

Each selected flow uses:

1. `vitis-execution-plan.json` — strict requested work, inputs, hashes,
   toolchain, timeouts, and output paths.
2. `vitis/commands.json` — exact rendered argv, owner, working directory, log,
   and timeout for inspection.
3. `vitis/build_vitis_application.py` — generated only for an embedded
   platform/application build.
4. `vitis-result.json` — command exit codes, durations, logs, findings, output
   existence, and output hashes.

The schemas are:

- `contracts/vitis-execution-plan.schema.json`
- `contracts/vitis-result.schema.json`

The field-shape example is:

- `contracts/examples/vitis/vitis-execution-plan.json`

## Invocation

Validate the plan:

```bash
python3 scripts/v0_1_runner.py vitis \
  --run runs/<request_id> \
  --validate-only
```

Render the exact commands without invoking Vitis:

```bash
python3 scripts/v0_1_runner.py vitis \
  --run runs/<request_id> \
  --dry-run
```

Execute:

```bash
python3 scripts/v0_1_runner.py vitis \
  --run runs/<request_id>
```

The runner sources the plan's `settings64.sh` into a captured subprocess
environment and then executes argv directly. It does not interpolate plan
values into a shell command.

## Generated command forms

HLS or AIE compile:

```text
v++ --compile --mode <hls|aie> --target <hw|hw_emu>
    --config <config> [--part <part>] [--platform <xsa-or-xpfm>]
    --output <xo-or-libadf> <inputs...>
```

System link:

```text
v++ --link --target <hw|hw_emu> --platform <extensible-xsa>
    --config <system.cfg> [--config <additional.cfg> ...]
    --save-temps --temp_dir <dir> --log_dir <dir> --report_dir <dir>
    --jobs <n> --output <linked-xsa-or-xclbin> <xo-or-libadf...>
```

Package:

```text
v++ --package --target <hw|hw_emu> --platform <platform>
    --package.out_dir <dir> [--package.boot_mode <mode>] <linked-input>
```

Embedded platform and application:

```text
vitis -s runs/<request_id>/vitis/build_vitis_application.py
```

The generated Python uses `vitis.create_client()`,
`create_platform_component()`, `platform.build()`,
`create_app_component()`, and `app.build(target="hw")`. It imports only the
declared sources and uses the declared processor, OS, domain, DTB policy,
template, and sysroot.

## Ordering

- Fixed-XSA embedded-only flow:
  `Vivado signoff → fixed XSA → Vitis platform/application → ELF`.
- Acceleration flow:
  `component verification → v++ compile/link/package → Vivado signoff of
  generated evidence`.
- Combined flow:
  `v++ compile/link/package → embedded application against the linked platform
  → Vivado signoff`.

Hardware validation consumes the PASS implementation result and, when
applicable, hash-matched ELF, DTB, XCLBIN, and package artifacts from the PASS
Vitis result.

## Safety and deterministic failure

- The runner refuses to replace a Vitis workspace unless it contains the
  matching `.vitis-runner-owned` request marker.
- Tool paths and all functional inputs are structured fields.
- Recorded input hashes are checked before execution.
- Every stage has a bounded timeout and a dedicated log.
- A non-zero exit, timeout, missing required output, hash mismatch, `DRY_RUN`,
  or invalid result prevents workflow PASS.
