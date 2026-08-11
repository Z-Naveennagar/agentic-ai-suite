<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AXI and Ready/Valid Interface Guidelines

Sources: UG1037 and the AMBA AXI specification. Use AMD AXI VIP or equivalent protocol
checking for functional verification.

## IF-1 — VALID must not depend on READY

A source asserts `VALID` when it has a transfer and keeps `VALID` and the payload stable until
`VALID && READY`. It must not wait for `READY` before asserting `VALID`. A destination can
compute `READY` from local capacity; implementations should avoid combinational paths between
interface inputs and outputs when required by the AXI interface and timing architecture.

```systemverilog
wire fire = m_valid && m_ready;

always_ff @(posedge clk) begin
  if (rst) begin
    m_valid <= 1'b0;
  end else if (m_ready || !m_valid) begin
    m_valid <= next_valid;
    if (next_valid)
      m_data <= next_data;
  end
end
```

The `m_ready || !m_valid` condition permits replacement of a consumed beat in the same cycle
and avoids an avoidable throughput bubble.

## IF-2 — Hold the complete payload while stalled

When `VALID && !READY`, keep `VALID` and every payload/sideband signal stable, including
`TDATA`, `TKEEP`, `TSTRB`, `TLAST`, `TID`, `TDEST`, and `TUSER` when present.

```systemverilog
assert property (@(posedge clk) disable iff (rst)
  m_valid && !m_ready |=> m_valid && $stable({m_data, m_keep, m_last}));
```

## IF-3 — Choose buffering by the timing boundary

A one-entry registered output can sustain one beat per cycle while allowing a combinational
READY path:

```systemverilog
assign s_ready = !out_valid || m_ready;
assign m_valid = out_valid;
assign m_data  = out_data;

always_ff @(posedge clk) begin
  if (rst) begin
    out_valid <= 1'b0;
  end else if (s_ready) begin
    out_valid <= s_valid;
    if (s_valid)
      out_data <= s_data;
  end
end
```

If both forward and READY paths must be registered, use a verified two-entry elastic buffer,
an AMD AXI Register Slice, or an XPM FIFO configured for the required latency. Do not label a
single capture register as a two-entry skid buffer, and verify randomized backpressure with no
loss, duplication, reordering, or bubbles beyond the selected architecture.

## IF-4 — Handle AXI4-Lite channels independently

AXI4-Lite has independent write-address and write-data channels. `AWVALID/AWREADY` and
`WVALID/WREADY` can handshake in either order or in the same cycle. A slave that supports one
outstanding write can still latch the address and data independently and issue `BVALID` only
after both have been accepted.

Similarly, accept `ARVALID/ARREADY` according to the read-side capacity, then hold `RVALID`,
`RDATA`, and `RRESP` until the response handshake. Treat "one outstanding" as an explicit
implementation limit, not a protocol property.

Verify at minimum:

- AW before W, W before AW, and simultaneous AW/W;
- response backpressure;
- read and write concurrency allowed by the implementation;
- reset while channels are idle and active; and
- byte-strobe behavior.

## Checklist

- [ ] A source never waits for READY before asserting VALID.
- [ ] VALID and all payload signals remain stable while stalled.
- [ ] A consumed output beat can be replaced without an unintended bubble.
- [ ] The chosen buffer actually has the claimed depth and registered paths.
- [ ] AXI4-Lite AW and W are captured independently.
- [ ] Protocol checker and randomized-backpressure tests pass.
