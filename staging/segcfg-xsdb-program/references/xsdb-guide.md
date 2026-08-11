# XSDB Programming Guide for Segmented Configuration

## Overview

XSDB (System Debugger) is a Tcl-based debug tool included with Vivado and Vitis that provides JTAG access to Versal devices. For Segmented Configuration, XSDB allows programming boot and PLD PDIs directly without requiring a full PetaLinux build.

## Starting XSDB

```bash
# Launch from Vivado Tcl Console
# or from the command line:
xsdb

# Or in batch mode (non-interactive):
xsdb -interactive
```

## Connecting to Hardware

```tcl
# Connect to local hardware server (cs_server/hw_server must be running)
xsdb% connect

# Connect to a remote hardware server
xsdb% connect -url <hostname>:3121

# List available targets
xsdb% targets

# Select the Versal device (usually target 1 for PMC/device root)
xsdb% ta 1
```

## Programming Commands

```tcl
# Program a PDI image to the device
xsdb% device program <path_to_file>.pdi

# Example: program boot PDI
xsdb% device program project_1.runs/impl_1/<design>_boot.pdi

# Example: program PLD PDI (after boot PDI is loaded)
xsdb% device program project_1.runs/impl_1/<design>_pld.pdi
```

## Memory Access Commands

```tcl
# Read from memory (force bypasses standard AHB safety checks)
xsdb% mrd -force 0xa4000000

# Read multiple words
xsdb% mrd -force 0xa4000000 4

# Write to memory
xsdb% mwr -force 0xa4000000 0xdeadbeef

# Load binary file into DDR (for staging PLD PDI before U-Boot)
xsdb% dow -data <design>_pld.pdi 0x1000000
```

## Typical Test Flow for Segmented Configuration

### Test 1: Verify Boot-Only (PS-only) Operation

```tcl
xsdb% connect
xsdb% ta 1
xsdb% device program impl_1/<design>_boot.pdi
# Wait for PLM messages on UART console (no errors expected)

# Verify PL is NOT accessible
xsdb% mrd -force 0xa4000000
# Expected: Memory read error at 0xA4000000. AP transaction timeout
```

### Test 2: Full Segmented Configuration (Boot + PLD)

```tcl
# Power cycle board first, then reconnect
xsdb% connect
xsdb% ta 1

# Program boot PDI
xsdb% device program impl_1/<design>_boot.pdi
# Check UART — PLM should complete boot sequence

# Program PLD PDI
xsdb% device program impl_1/<design>_pld.pdi
# Check UART — PLM should apply PL isolation, load PL, release isolation

# Verify PL IS accessible
xsdb% mrd -force 0xa4000000
# Expected: A4000000: 00000000

xsdb% mwr -force 0xa4000000 0xdeadbeef
xsdb% mrd -force 0xa4000000
# Expected: A4000000: DEADBEEF
```

### Test 3: PL Reload Verification

```tcl
# Define goto_pmc once at the top of your script.
# Rules:
#   - Do NOT use bare "ta 1": target indices shift after boot.pdi executes.
#   - Do NOT call "target -set -filter" directly from a CPU context (ta 20 / ta 31):
#     the filter searches relative to the current subtree and fails on the 3rd+ reload
#     with PLM Error 0x2101/0x36 (CDO processing error).
#   - goto_pmc re-anchors at device root first, making PMC selection reliable.
proc goto_pmc {} {
  ta 1
  after 500
  target -set -filter {name =~ "PMC*"}
  after 1000
}

# Before every PLD reload — works whether or not CPU targets were used in between
goto_pmc
xsdb% device program impl_1/<design2>_pld.pdi

# PLM applies isolation, loads new PL, releases isolation
# Verify new PL behavior
xsdb% mrd -force 0xa4000000
```

## Common Issues

| Symptom | Likely Cause | Resolution |
|---------|-------------|-----------|
| `AP transaction timeout` on mrd | PL not configured | Load the pld.pdi first |
| PLM error on pld.pdi load | UID mismatch | Ensure pld.pdi was compiled from the same PS domain as boot.pdi |
| No UART output after boot.pdi | PLM startup issue | Check PLM error codes; verify board connections |
| `device program` hangs | JTAG connectivity issue | Check cable, restart hw_server, reconnect |
| PLM Error Major 0x2101 Minor 0x36 on 2nd/3rd PLD load — no CPU tests | `ta 1` no longer targets PMC after boot.pdi executes; target indices shift | Replace `ta 1` with `target -set -filter {name =~ "PMC*"}` + `after 500` before every PLD load |
| PLM Error Major 0x2101 Minor 0x36 on 3rd PLD load — with DDR/CPU tests between loads | After `ta 20` (Cortex), `target -set -filter {name =~ "PMC*"}` is unreliable when called directly from a CPU context | Use `goto_pmc` helper: `ta 1` → `after 500` → `target -set -filter {name =~ "PMC*"}` → `after 1000` before every PLD load |
|Context does not support memory read. Unsupported command | target is not set to APU/RPU | `target -set -filter {name =~ "APU*"}` before read from Slave IP | 
## Hardware Server Management

```bash
# Start hardware server (on the machine connected to the board)
hw_server

# Start at specific port
hw_server -s TCP::<port>

# Connect XSDB to remote server
xsdb% connect -url <remote_host>:3121
```
