<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# RTL Elaboration Analysis Report — Example (Clean Design)

```markdown
# RTL Elaboration Analysis Report

## Summary
| Severity | Count | Actionable | Advisory |
|----------|-------|------------|----------|
| Error | 0 | 0 | 0 |
| Critical Warning | 0 | 0 | 0 |
| Warning | 0 | 0 | 0 |

- **Log File:** [synth_1/runme.log](../../project_1.runs/synth_1/runme.log)
- **Analysis Status:** ✅ **PASSED — no elaboration issues**
- **Total Messages:** 0

## Elaboration Results

✅ **Vivado elaboration completed without errors or warnings.**

The RTL design passes all Verific front-end checks. The recommendations below are
best-practice coding guidelines from UG901.

## Best Practice Recommendations (Optional)

1. **Use `always_comb` / `always_ff` (SystemVerilog)**
   - Replaces `always @(*)` and `always @(posedge clk)` with stronger intent checks
   - Reference: IEEE 1800-2017 §9.2.2

2. **Use `process(all)` (VHDL-2008)**
   - Replaces explicit sensitivity lists with automatic coverage
   - Requires `-vhdl2008` project setting
   - Reference: IEEE 1076-2008 §11.3

3. **Initialize Outputs at Top of Combinational Blocks**
   - Prevents latch inference even as code evolves
   - Reference: UG901 Ch.4.3.1

4. **Prefer Named Port Connections**
   - `.port(signal)` style catches connection errors at elaboration time
   - Reference: UG901 Ch.4.1

## Next Steps

- Design is elaboration-clean — proceed with full synthesis or `rtl-lint` for deeper analysis
- Consider applying best-practice recommendations for production code
```
