


# Board Farm Cluster Information 
| Board cluster | Board Name | Board Part | Part Number | Notes |
|-------|-------------|------------------|------------------|-------|
| vck190-1 till vck190-5, vck190-11 till vck190-16, vck190-19 till vck190-24| VCK190 | xilinx.com:vck190:part0:3.3 | xcvc1902-vsva2197-2MP-e-S |  Versal AI Core Series |
| pcie_x86-16 | VnX | N/A | xcvn3716-vsvb2197-2LHPV-e-L |  Versal KSB |
| vek385-11 till vek385-16 | VEK385 Rev A | vek385:part0:1.1 | xc2ve3858-ssva2112-2MP-e-S |  Versal Prime Series Gen 2 |
| vek280-1 till vek280-12 | VEK280 | xilinx.com:vek280:part0:1.2 | xcve2802-vsvh1760-2MP-e-S | Versal AI Edge Series |
| vrk160-1 till vrk160-6 | VRK160 | xilinx.com:vrk160:part0:1.2 | xcvr1602-vsva2488-2MP-e-S-es1 | Versal RF Series ES1 |

#Connect to Board
```bash
systest $(Board Cluster) ./${CLAUDE_SKILL_DIR}/scripts/run_board.cmd
```

#Mandatory pre-requisites for pcie_x86-16 programming

```tcl
#Mandatory pre-requisites for VnX board
ta 1
rst -type por
mwr -force 0xF1260200 0x0100
mwr -force 0xF1110004 0x0
target -set -filter {name =~ "PMC*"}
rst -system
after 200
```

## Repeated PLD Loads on KSB (pcie_x86-16)

**Do NOT use `ta 1` alone between PLD loads.** After `boot.pdi` executes, target indices
shift and `ta 1` no longer selects PMC. Using it before a 2nd or 3rd PLD load causes:

```
PLM Error Major 0x2101 Minor 0x36 occurred during programming
```

### PLD-only sequence (no CPU target switches between loads)

When no DDR/CPU tests are interleaved, `target -set -filter` + `after 500` is sufficient:

```tcl
target -set -filter {name =~ "PMC*"}
after 500
device program ./design_pld.pdi
```

### PLD sequence with DDR tests between loads (ta 20 / Cortex-A78 context)

After switching to a CPU target (`ta 20`) for DDR access, `target -set -filter {name =~ "PMC*"}`
called directly from that context is unreliable on the 3rd+ reload (PLM Error 0x2101/0x36).
The filter needs the hierarchy re-anchored at device root first.

**Correct `goto_pmc` helper** — use before every PLD load when CPU targets are involved:

```tcl
proc goto_pmc {} {
  ta 1
  after 500
  target -set -filter {name =~ "PMC*"}
  after 1000
}

# DDR test
ta 20
wr_rd_test ...

# Back to PMC for PLD reload
goto_pmc
device program ./design_pld.pdi
```
## Issues with reserving Board from Farm 

### Check available board alternatives in group

| Board cluster | Board group |
|-------|-------------|
| vck190-1 | vck190 |
| vek385-11 | vek385 |
| vrk160-1 | vrk160 |
| vek280-1 | vek280 |

```bash

cluster-ping <Board group>

```

