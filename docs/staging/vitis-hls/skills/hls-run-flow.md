<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# /hls-run-flow — Run the HLS Flow

Run one of the four Vitis HLS flow stages — C Simulation (csim), C Synthesis (csynth), C/RTL Co-Simulation (cosim), or Implementation (impl) — for a given HLS component.

| Field | Value |
|-------|-------|
| **Argument hint** | `<hls config path $CONFIG>` |
| **Bundle path** | `vitis-hls-ai-assistant-skills/hls-run-flow/SKILL.md` |

## Keyword Routing

| User keyword | Flow triggered |
|--------------|----------------|
| run csim | C Simulation |
| run csynth | C Synthesis |
| run cosim | C/RTL Co-Simulation |
| run impl | Implementation |

If the keyword doesn't match, the skill asks the user to clarify.

## Prerequisite Gates

- Before **cosim**: `$WORK_DIR/hls/syn/` must exist (csynth done)
- Before **impl**: `$WORK_DIR/hls/sim/` must exist (cosim done)

## Execution

**Inside the IDE (preferred):** Calls `runHlsActiveComponentByType` with the appropriate stage index.

**Outside the IDE (shell fallback):**

=== "C Simulation"
    ```bash
    vitis-run --mode hls --config $CONFIG --work_dir $WORK_DIR --csim
    ```

=== "C Synthesis"
    ```bash
    v++ --compile --mode hls --config $CONFIG --work_dir $WORK_DIR
    ```

=== "Co-Simulation"
    ```bash
    vitis-run --mode hls --config $CONFIG --work_dir $WORK_DIR --cosim
    ```

=== "Implementation"
    ```bash
    vitis-run --mode hls --config $CONFIG --work_dir $WORK_DIR --impl
    ```

## Out of Scope

- Editing C source, pragmas, or `hls_config.cfg` directives (use [`/hls-optimize`](hls-optimize.md))
- Vivado-side timing closure beyond post-route reporting

<p class="sphinxhide" align="center"><sub>Copyright © 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
