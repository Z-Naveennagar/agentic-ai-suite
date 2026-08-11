<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Example Prompts

Guided debug prompt scripts for ChipScope MCP. Paste these into your
MCP-enabled AI client (VS Code + Copilot, Cursor, or Claude Code) with the
`chipscope` server connected and running. Each prompt builds on the previous
one — wait for a response before sending the next.

!!! tip "Tested boards"
    These scripts were verified on **VPK120** (`xcvp1202`, GTM + GTYP
    transceivers) and **VCK190** (`xcvc1902`, GTY transceivers), but the
    same prompt patterns apply to any AMD Versal™ device.

## IBERT serial links

```text
List the IBERT cores on the device and tell me what transceiver types are available
```

On a board with both transceiver types (like VPK120), you'll see **GTM**
(56+ Gbps, uses YK scan) and **GTYP** (32 Gbps, uses traditional eye scan).
ChipScope MCP auto-detects the transceiver type and steers the AI client to
the correct scan tool — asking for an eye scan on a GTM link fails clearly
with a pointer to YK scan, and vice versa.

### GTM — YK scan

```text
For IBERT Versal GTM, create a link on channel 0, with PRBS 31 pattern and Near-End PMA loopback. With that link, show me a YK scan.
```

The AI client finds the GTM IBERT core and its first GT group, creates a
loopback link on channel 0 (TX feeds back to RX), configures the PRBS 31
pattern and loopback mode, then runs the YK scan and returns SNR statistics
and slicer waveform data.

### GTYP / GTY — eye scan

```text
For IBERT Versal GTYP, create a new link on channel 0, with PRBS 31 pattern and Near-End PMA loopback. With that link, show me an eye scan.
```

The AI client finds the GTYP (or GTY) IBERT core and its first GT group,
creates the loopback link, configures the pattern and loopback mode, then
runs the eye scan and returns a BER heatmap. To save the plot to a file:

```text
Run an eye scan on that link and save the plot to eye_scan.png
```

!!! note
    `chipscope_ibert_yk_scan` doesn't apply to GTY/GTYP links — if you ask
    for a YK scan on one, the tool reports that the link uses eye scan
    instead.

## Board-to-scan matrix

| Board | Transceiver(s) | Recommended scan |
|-------|----------------|-------------------|
| VCK190 | GTY (32 Gbps) | GTY **eye scan** (BER). YK scan N/A. |
| VPK120 | GTM (56+ Gbps), GTYP (32 Gbps) | GTM **YK scan** (SNR); GTYP **eye scan** (BER) |

## Key points

1. **Multiple debug domains in one session** — DDR calibration, serial link
   scans, and logic-analyzer captures are all reachable through natural
   language prompts, without scripting or the Vivado GUI.
2. **Transceiver auto-detection** — ChipScope MCP inspects the link and
   steers the AI client to the correct scan tool (eye scan vs. YK scan).
3. **Single-sentence prompts** — the AI client discovers the hardware
   hierarchy, configures links, and runs scans from one goal-oriented
   sentence rather than a list of API calls.
4. **Visual output** — DDR eye scans, IBERT eye scans, and YK scans return
   inline PNG visuals in chat by default.

## More examples

For hands-on walkthroughs with complete designs and step-by-step prompts, see the example directories in `agentic-ai-suite`:

- **chipscope-mcp/all-tools** — ChipScoPy MCP All-Tools Validation: exercises all 13 chipscope-mcp tools on a VCK190 (session, device, scan, VIO, ILA, SysMon, NoC, DDR, sysdbg)
- **hw-ila-debug/axi-protocol-capture** — ILA AXI Protocol Capture: AXI-Lite and AXI-Stream capture with a System ILA, traffic driven via VIO
- **hw-vio-debug/axi-register-rw** — VIO AXI Register Read/Write: VIO-controlled AXI-Lite register access and AXI-Stream packet generation
- **hw-noc-debug** — four NoC error scenarios: write-decode-error, axsize-violation, burst-4k-crossing, write-timeout

## Next steps

- **[Tool Reference](../../reference/chipscope-tools.md)** — the full ChipScope MCP tool
  catalog, including `display` modes and file-export options for scans.

<p class="sphinxhide" align="center"><sub>Copyright © 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
