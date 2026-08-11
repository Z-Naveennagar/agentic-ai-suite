<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Finite-State Machine Guidelines

Sources: UG901 FSM coding techniques and `FSM_ENCODING`/`FSM_SAFE_STATE` attributes.

## FSM-1 — Use a recognizable synchronous FSM

Use a registered current state, complete next-state logic, and nonblocking assignments in the
state register. Register outputs when required for timing or glitch-free behavior.

Vivado's default `FSM_ENCODING="auto"` selects an encoding using synthesis heuristics. Do not
force one-hot, sequential, Gray, or another encoding without an area, power, safety, or timing
reason. Verify the encoding applied by synthesis.

```systemverilog
typedef enum logic [1:0] {IDLE, RUN, DONE} state_t;
(* FSM_ENCODING = "auto" *) state_t state_q, state_d;

always_ff @(posedge clk) begin
  if (rst)
    state_q <= IDLE;
  else
    state_q <= state_d;
end

always_comb begin
  state_d = state_q;
  unique case (state_q)
    IDLE: if (start) state_d = RUN;
    RUN:  if (last)  state_d = DONE;
    DONE:             state_d = IDLE;
    default:          state_d = IDLE;
  endcase
end
```

## FSM-2 — Request safe-state hardware when recovery is required

A source-code `default` branch alone does not guarantee that illegal-state recovery hardware
is preserved after FSM optimization. When the safety requirement needs hardware recovery,
apply `FSM_SAFE_STATE` to the state register and choose the documented value that matches the
contract, such as `reset_state` or `default_state`.

```systemverilog
(* FSM_ENCODING = "auto", FSM_SAFE_STATE = "default_state" *) state_t state_q, state_d;
```

Retain a defined default transition and verify the synthesized property. Prove recovery with
illegal-state injection or formal analysis; `report_drc` is not sufficient.

## FSM-3 — Keep outputs and coverage explicit

Assign defaults before the case statement to avoid latches. Avoid `full_case`/`parallel_case`
pragmas that can hide uncovered behavior. If outputs are combinational functions of state,
consider registering them when glitches or timing are concerns.

## Checklist

- [ ] Vivado recognizes the intended FSM.
- [ ] All next-state and output paths are assigned without unintended latches.
- [ ] Encoding is `auto` unless another encoding is justified and verified.
- [ ] A required recovery FSM uses `FSM_SAFE_STATE`, not only a default branch.
- [ ] Illegal-state behavior is tested when recovery is a requirement.
