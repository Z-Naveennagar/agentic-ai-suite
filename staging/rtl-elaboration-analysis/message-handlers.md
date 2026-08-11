<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Elaboration Message Handlers

Per-message-ID fix instructions for Vivado Verific front-end elaboration messages.
Messages appear as `[Synth 8-XXX]` in Vivado logs. The internal ID maps to the Synth 8
message number.

> **Mandatory**: For every message, read the RTL source at the reported file:line using
> `read_file` before generating a fix. Never fabricate code.

---

## How Messages Appear in Vivado Logs

```
ERROR: [Synth 8-128] 'my_signal' is not declared [/path/to/file.v:42]
WARNING: [Synth 8-566] inferring latch for variable 'state_reg' [/path/to/file.v:100]
CRITICAL WARNING: [Synth 8-637] variable 'data' cannot be written by both continuous and procedural assignments [/path/to/file.v:55]
```

The parser extracts: severity, ID (128/566/637), message text, file path, line number.

---

## Resolution Guides

For messages with detailed resolution guides, a `→ resolution/<file>.md` reference
appears in the Fix Strategy column. Load the guide with `read_file` for step-by-step
fix instructions with code templates. See `resolution-guide.md` for the full index.

---

## Dispatch Table — Verilog/SystemVerilog (VLOG)

### Tier 1 — Directly Fixable

| ID | Severity | Short Name | Fix Strategy |
|----|----------|------------|--------------|
| 117 | warning | undefined macro | Add `` `define`` or fix macro name typo |
| 126 | error | redeclaration | Remove duplicate declaration → `resolution/declaration.md` |
| 128 | error | undeclared variable | Add missing declaration → `resolution/VLOG-128.md` |
| 129 | error | port direction not declared | Add `input`/`output`/`inout` direction → `resolution/declaration.md` |
| 131 | error | port not in port list | Add port to module header → `resolution/declaration.md` |
| 132 | error | parameter on LHS | Change to `localparam` or use variable instead |
| 133 | error | net on LHS of procedural | Change `wire` to `reg`/`logic` → `resolution/VLOG-133.md` |
| 134 | error | variable on LHS of continuous | Change `reg` to `wire` or use `always` block → `resolution/VLOG-134.md` |
| 142 | error | mixed named/ordered ports | Convert all connections to named style → `resolution/port-connection.md` |
| 143 | error | duplicate port connection | Remove the duplicate `.port()` → `resolution/port-connection.md` |
| 144 | error | mixed named/ordered params | Convert all overrides to named style → `resolution/port-connection.md` |
| 145 | error | duplicate parameter override | Remove the duplicate `#(.PARAM())` → `resolution/port-connection.md` |
| 148 | error | parameter has no value | Assign a default value |
| 150 | error | multiple defaults in case | Remove extra `default:` blocks → `resolution/case-statement.md` |
| 510 | error | mixed port directions | Split into separate port expressions → `resolution/port-connection.md` |
| 512 | error | too many port connections | Remove excess positional connections → `resolution/port-connection.md` |
| 530 | critical | const variable reassigned | Remove the reassigning statement → `resolution/constant-expr.md` |
| 544 | warning | negative replication count | Fix replication expression to be positive → `resolution/constant-expr.md` |
| 545 | warning | zero replication count | Fix replication expression or remove concat → `resolution/constant-expr.md` |
| 589 | warning | same-named implicit nets | Add explicit `wire` declaration |
| 593 | warning | instance label required | Add instance label before module name |
| 599 | error | duplicate declaration | Remove the duplicate → `resolution/declaration.md` |
| 615 | error | duplicate enum value | Assign unique enum values → `resolution/declaration.md` |
| 624 | error | undeclared type | Add type declaration or `import pkg::*` → `resolution/declaration.md` |
| 630 | error | same genvar in nested loop | Rename inner genvar → `resolution/generate-loop.md` |
| 636 | error | type used before declaration | Move declaration before first use → `resolution/declaration.md` |
| 637 | critical | dual driver (continuous+procedural) | Pick one assignment style and remove the other → `resolution/VLOG-637.md` |
| 649 | warning | port unconnected | Connect port or explicitly leave open → `resolution/port-connection.md` |

### Tier 2 — Fixable with RTL Context

| ID | Severity | Short Name | Fix Strategy |
|----|----------|------------|--------------|
| 506 | warning | case item never executed | Read case statement; remove dead item with x/z/out-of-range → `resolution/case-statement.md` |
| 507 | warning | unreachable case item | Read case statement; remove or reorder items → `resolution/case-statement.md` |
| 508 | warning | overlapping case items | Read case statement; fix overlapping values → `resolution/case-statement.md` |
| 511 | error | named port doesn't exist | Search module definition for closest port name (typo fix) → `resolution/VLOG-511.md` |
| 513 | warning | too few port connections | Add missing positional connections → `resolution/port-connection.md` |
| 514 | warning | port width mismatch | Read both declarations; fix signal width or add slice → `resolution/VHDL-759.md` |
| 519 | error | no field in class | Search class definition for closest field name → `resolution/VLOG-511.md` |
| 546 | error | unresolved identifier | Search workspace for declaration; add import/include → `resolution/VHDL-833.md` |
| 547 | warning | index out of range | Read declaration; fix index to be within bounds → `resolution/range-index.md` |
| 548 | error | part-select out of range | Read declaration; adjust select range → `resolution/range-index.md` |
| 549 | error | part-select direction mismatch | Read declaration; swap MSB:LSB or LSB:MSB → `resolution/range-index.md` |
| 560 | error | mixed level/edge sensitivity | Separate into two always blocks (combo + sequential) → `resolution/clock-edge.md` |
| 561 | error | no clock in event control | Add clock signal after `posedge`/`negedge` → `resolution/clock-edge.md` |
| 562 | error | ambiguous clock | Use standard async reset pattern (if/else) → `resolution/clock-edge.md` |
| 563 | warning | multiple event controls | Remove internal `@(...)` or split into separate always blocks → `resolution/clock-edge.md` |
| 564 | warning | incomplete sensitivity list | Add missing signal to `@(...)` or use `@(*)` → `resolution/VLOG-564.md` |
| 566 | warning | inferring latch | Add `else`/`default` branch to make combinational logic complete → `resolution/VLOG-566.md` |
| 570 | error | generate expression not constant | Replace variable with `parameter`/`localparam` → `resolution/constant-expr.md` |
| 576 | error | type mismatch | Read both types; add cast or change declaration → `resolution/type-mismatch.md` |
| 577 | error | no field in struct | Search struct definition for closest field name → `resolution/VLOG-511.md` |
| 579 | error | expression must be constant | Replace with `parameter`/`localparam` value → `resolution/constant-expr.md` |
| 580 | error | must be packed type | Add `packed` keyword to type definition → `resolution/type-mismatch.md` |
| 581 | error | illegal genvar use | Move genvar use inside generate block → `resolution/generate-loop.md` |
| 583 | error | packed union size mismatch | Pad union members to equal bit width → `resolution/type-mismatch.md` |
| 585 | warning | always_ff no event control | Add `@(posedge clk)` event control → `resolution/VLOG-564.md` |
| 591 | error | interface mismatch | Fix interface type at instantiation site → `resolution/type-mismatch.md` |
| 592 | error | modport mismatch | Fix modport name at instantiation site → `resolution/type-mismatch.md` |
| 596 | error | unconnected interface port | Connect the interface port → `resolution/port-connection.md` |
| 597 | error | hierarchical name unresolved | Fix hierarchical path — search design for correct path → `resolution/port-connection.md` |
| 598 | error | no signal for .* | Add matching signal declaration or use named port → `resolution/port-connection.md` |
| 602 | error | generic interface unresolved | Specify concrete interface type → `resolution/port-connection.md` |
| 603 | error | edge condition mismatch | Align `if` condition operand with sensitivity list edges |
| 616 | error | enum value doesn't fit | Widen enum base type or fix value |
| 617 | error | no signal for port connection | Fix signal name or add declaration → `resolution/VHDL-833.md` |
| 618 | error | variable too large | Reduce width or restructure |
| 622 | error | packed range on unpacked type | Remove packed dimension or change to packed type → `resolution/type-mismatch.md` |
| 626 | warning | divide by zero | Add divisor != 0 guard or fix expression |
| 631 | warning | all outputs unconnected | Connect outputs or remove unused instance → `resolution/port-connection.md` |
| 645 | warning | blocking/non-blocking mix | Use consistent `<=` (sequential) or `=` (combinational) → `resolution/VLOG-645.md` |
| 646 | warning | input port has internal driver | Remove internal driver or change port to `output` → `resolution/port-connection.md` |
| 644 | critical | config rule conflict | Fix configuration hierarchy binding |
| 647 | critical | hier name in param unresolved | Replace with constant expression → `resolution/constant-expr.md` |
| 648 | critical | non-constant param override | Replace with constant expression → `resolution/constant-expr.md` |
| 650 | critical | nested interface scope | Flatten interface usage or pass items explicitly |

### Tier 3 — Advisory Only

| ID | Severity | Short Name | Reason Not Auto-Fixable |
|----|----------|------------|------------------------|
| 98 | warning | unimplemented feature | Requires rewrite with supported construct |
| 99 | error | unimplemented feature | Requires rewrite with supported construct |
| 100 | error | syntax error | Parser failure — message itself describes fix |
| 101 | error | unsupported construct | Requires architectural redesign |
| 102 | warning | ignoring construct | Informational — no code change needed |
| 103 | warning | directive ignored | Informational |
| 104 | warning | pragma ignored | Informational |
| 105 | error | missing terminating " | Fix string literal — parser indicates location |
| 106 | error | missing closing */ | Find unclosed block comment |
| 107 | warning | missing translate on | Add `// synthesis translate_on` |
| 109 | error | include file not found | Fix include path or add file — project setup issue |
| 110–116 | error | macro argument errors | Fix macro definition/invocation — parser indicates issue |
| 118–119 | warning | macro redefined | May be intentional; review define guard |
| 121–123 | error | ifdef/endif mismatch | Fix preprocessor nesting |
| 124 | warning | unsupported declaration | Informational — synthesis limitation |
| 125 | error | invalid declaration | Requires rewrite |
| 151 | warning | ignoring attribute | Informational |
| 152 | warning | min:typ:max | Informational — simulation semantics |
| 153 | warning | case/wildcard equality replaced | Informational |
| 200 | warning | overwriting module | May be intentional; check for duplicate source files |
| 402 | error | failed synthesizing | Meta-error — root cause is another message |
| 404 | warn/err | module not found | Missing file or library — project setup |
| 405 | error | no modules found | Project setup issue |
| 525 | warning | initial assign ignored for synth | Synthesis semantics — informational |
| 526 | warning | tagged union as normal | Tool limitation |
| 527 | warning | initial block non-constant | Informational |
| 532 | error | signed divider unsupported | Requires algorithm redesign |
| 533 | error | exponentiation unsupported | Requires algorithm redesign |
| 550 | error | var bit-select on LHS | Requires assignment restructuring |
| 551 | error | condition not constant | Requires loop restructuring |
| 552–555 | error | loop/call depth exceeded | Requires algorithmic restructuring |
| 554 | error | module recursion | Requires design restructuring |
| 565 | warning | no event control | Requires understanding design intent |
| 567 | warning | ambiguous clock const | Informational |
| 569 | warning | initial block ignored | Informational |
| 571 | warning | unsupported system call | Remove/guard for synthesis |
| 572 | warning | missing Liberty info | Library issue, not RTL |
| 574 | warning | fork/join sequential | Synthesis limitation |
| 575 | warning | negative shift as unsigned | Informational |
| 601 | warning | blackbox .* unconnected | Blackbox limitation |
| 604 | warning | iff condition ignored | Informational |
| 609 | warning | blackbox array 1-bit ports | Blackbox limitation |
| 613 | warning | inout inferred, no modport | May be intentional |
| 614 | warning | ignoring power pin | Cell library issue |
| 620 | error | sim-only file | Remove sim-only file from synthesis |
| 629 | warning | pragma on bits ignored | Informational |
| 632 | critical | mem data not found | External file issue |
| 634 | warning | $warning | User's own `$warning` — informational |
| 641 | warning | multiple config tops | Configuration issue |

---

## Dispatch Table — VHDL

### Tier 1 — Directly Fixable

| ID | Severity | Short Name | Fix Strategy |
|----|----------|------------|--------------|
| 730 | error | no such generic | Fix generic name (typo check) or remove → `resolution/VLOG-511.md` |
| 731 | error | no such port | Fix port name (typo check) or remove → `resolution/VLOG-511.md` |
| 750 | error | duplicate choice in aggregate | Remove duplicate choice → `resolution/case-statement.md` |
| 751 | error | mixed named/positional aggregate | Use one style consistently |
| 752 | error | too many generics | Remove excess generic associations |
| 753 | error | too many ports | Remove excess port associations |
| 755 | error | generic has no value | Assign a value or add default |
| 770 | warning | duplicate enum encoding | Assign unique encoding values |
| 774 | error | duplicate association | Remove the duplicate → `resolution/port-connection.md` |
| 775 | error | missing association | Add the missing port/generic mapping → `resolution/port-connection.md` |
| 814 | error | previously used choice | Remove or change the duplicate case choice → `resolution/case-statement.md` |
| 841 | error | protected type var initialized | Remove the initializer (`:= ...`) → `resolution/declaration.md` |
| 856 | error | constant must have value | Add `:= <value>` to constant declaration → `resolution/declaration.md` |

### Tier 2 — Fixable with RTL Context

| ID | Severity | Short Name | Fix Strategy |
|----|----------|------------|--------------|
| 608 | error | external name type mismatch | Read both declarations; fix type to match → `resolution/type-mismatch.md` |
| 609 | error | protected type for declaration | Use a different (synthesizable) type |
| 701 | error | already constrained array | Remove redundant constraint |
| 740 | error | array size mismatch | Read both sides; fix dimensions |
| 742 | error | index out of range | Read declaration; fix index → `resolution/range-index.md` |
| 744 | error | constant required | Replace with constant/generic → `resolution/constant-expr.md` |
| 745 | error | slice direction mismatch | Read declaration; swap `to`/`downto` → `resolution/range-index.md` |
| 746 | error | overlapping case choice | Read case type; fix choice values → `resolution/case-statement.md` |
| 747 | error | missing case choice | Read type definition; add `when others` or explicit choices → `resolution/VHDL-747.md` |
| 754 | error | unconstrained array | Add index constraint |
| 758 | warning | signal not in sensitivity list | Add signal to sensitivity list or use `(all)` (VHDL-2008) → `resolution/VLOG-564.md` |
| 759 | error | width mismatch in assignment | Read both declarations; resize source or target → `resolution/VHDL-759.md` |
| 760 | error | logical operator length mismatch | Read both operands; resize to match → `resolution/VHDL-759.md` |
| 761 | error | array aggregate width mismatch | Fix element expression width → `resolution/VHDL-759.md` |
| 762 | error | record aggregate width mismatch | Fix element expression width |
| 766 | error | expression out of range | Fix value or widen type → `resolution/range-index.md` |
| 767 | error | no such attribute | Fix attribute name (typo check) → `resolution/VLOG-511.md` |
| 768 | error | design unit not found | Fix unit name or add `library`/`use` clause → `resolution/VHDL-833.md` |
| 769 | critical | null range | Fix range bounds (left should differ from right) → `resolution/range-index.md` |
| 771 | error | unit not found in library | Fix library or unit name → `resolution/VHDL-833.md` |
| 773 | error | missing body | Add package/entity body |
| 777 | error | record element not found | Search record type; fix element name (typo) → `resolution/VLOG-511.md` |
| 778 | error | no matching formal generic | Add generic to entity or fix component declaration |
| 779 | error | no matching formal port | Add port to entity or fix component declaration |
| 781 | error | port width mismatch | Read both declarations; fix actual width → `resolution/VHDL-759.md` |
| 789 | error | missing aggregate elements | Add missing elements or `others => ...` |
| 790 | error | missing case choices | Add `when others` or missing alternatives → `resolution/VHDL-747.md` |
| 793 | error | port type mismatch | Read both types; fix actual type → `resolution/type-mismatch.md` |
| 794 | error | generic type mismatch | Read both types; fix actual type → `resolution/type-mismatch.md` |
| 795 | warning | port direction mismatch | Fix direction in component or entity |
| 803 | error | integer out of type range | Clamp or widen type range → `resolution/range-index.md` |
| 805 | error | unconstrained return | Add return type constraint |
| 806 | error | integer overflow | Fix assigned value to be within range → `resolution/range-index.md` |
| 812 | warning | clock used as data | Separate clock and data paths |
| 815 | error | no such architecture | Fix architecture name |
| 817 | error | cannot infer flip-flop | Fix clocked process structure (add clock edge) |
| 818 | error | signal already used as clock | Don't reuse clock signal as data |
| 819 | warning | invalid ram attribute | Move `ram_style` attribute to actual memory variable |
| 823 | error | driven twice in process | Remove second driver or merge into single assignment → `resolution/VLOG-637.md` |
| 825 | error | value out of allowable range | Fix value or widen range → `resolution/range-index.md` |
| 827 | error | aggregate range direction mismatch | Fix `to`/`downto` to match → `resolution/range-index.md` |
| 828 | critical | dontcares in slices | Remove explicit don't-cares from slice expressions |
| 830 | warning | port missing in component | Add port to component declaration |
| 831 | warning | port width mismatch (integer) | Fix width at connection |
| 833 | error | unknown identifier | Search workspace; fix name, add declaration, or add `use` → `resolution/VHDL-833.md` |
| 837 | warning | expecting unsigned | Cast expression to unsigned |
| 838 | warning | case choice out of range | Fix choice value to be within select range → `resolution/case-statement.md` |
| 839 | error | invalid assignment to type | Fix assignment target → `resolution/type-mismatch.md` |
| 840 | error | concat width mismatch | Fix concatenation widths → `resolution/type-mismatch.md` |
| 842 | error | non-contiguous association | Fix port association to be contiguous |
| 849 | warning | case/choice width mismatch | Fix case expression or choice widths to match → `resolution/case-statement.md` |
| 857 | error | generic width mismatch | Fix actual generic width to match formal → `resolution/VHDL-759.md` |
| 858 | error | non-input function port | Change to `in` mode for function parameter |
| 864 | error | unconstrained subtype | Add constraint (or use VHDL-2008 mode) |
| 866 | error | unconstrained signal | Add index constraint to array type |
| 867 | error | function arg size mismatch | Fix argument width → `resolution/VHDL-759.md` |
| 869 | error | out of bounds slice | Fix slice range to be within array bounds → `resolution/range-index.md` |
| 872 | warning | metalogical comparison | Replace metalogical value comparison with proper check |

### Tier 3 — Advisory Only

| ID | Severity | Short Name | Reason Not Auto-Fixable |
|----|----------|------------|------------------------|
| 598 | error | binary parse error | Internal file corruption |
| 599 | error | parsing error | Parser failure — message describes issue |
| 602 | error | failed synthesizing | Meta-error |
| 603 | error | unsupported construct | Requires design restructuring |
| 604 | error | unimplemented feature | Requires design restructuring |
| 605 | warning | unimplemented feature | Tool limitation |
| 606 | warning | ignoring unsynthesizable | Informational |
| 607 | error | unexpected node type | Internal elaboration error |
| 610 | warning | SV config generic ignored | Configuration issue |
| 615 | warning | library alias | Project setup |
| 617 | error | floating point exception | Algorithmic issue |
| 700 | error | miscellaneous error | Generic catch-all |
| 749 | warning | integer truncation | Informational |
| 756–757 | error | loop/call depth exceeded | Requires algorithmic restructuring |
| 776 | warning | division by zero | May need algorithmic redesign |
| 780 | error | OPEN with unconstrained | Requires port redesign |
| 782 | error | recursive instantiation | Design architecture issue |
| 783 | error | conflicting rebinding | Component binding issue |
| 784 | warning | missing liberty info | Library issue, not RTL |
| 785 | warning | null record field | May be intentional |
| 786 | warning | arith left shift as logical | Synthesis limitation |
| 788 | warning | global signal as local | Architecture limitation |
| 797 | warning | shared variable as local | VHDL semantics |
| 798 | error | user cell conflicts library | Library conflict |
| 804 | warning | null port ignored | Informational |
| 808 | error | failed to read VHDL | File access issue, not RTL |
| 816 | error | loop not converging | Requires algorithmic restructuring |
| 821 | warning | null assignment ignored | Informational |
| 824 | warning | negative power RHS | Requires redesign |
| 829 | warning | null init ignored | Informational |
| 832 | warning | attribute on constant | Informational |
| 845 | warning | index on null range | Informational |
| 855 | warning | failed Verific evaluate | Informational |
| 859 | warning | null type declaration | Informational |
| 861 | warning | null array component port | Informational |
| 873 | warning | null range expression | Informational |
| 874 | warning | exceed integer range | Informational |

---

## Detailed Handler Instructions

For each Tier 1/Tier 2 message, follow these steps:

### General Pattern

1. **Read source**: `read_file(file, line-10, line+10)` — get 20 lines of context
2. **Identify the construct**: Parse the message text for signal/port/type names
3. **Look up declarations**: For mismatches, read the declaration of both sides
4. **For typos**: Use `grep_search` or `file_search` to find the closest matching name
5. **Generate diff fix**: Show `- old` and `+ new` lines with inline comments

### VLOG-128: Undeclared Variable

```
ERROR: [Synth 8-128] 'my_signal' is not declared [file.v:42]
```

**Steps:**
1. Read file.v at line 42 to see usage context
2. Determine intended type from usage (LHS of `<=` → `reg`/`logic`, RHS only → `wire`)
3. Search module for similar names (fuzzy match for typos)
4. If typo found → fix the name
5. If genuinely missing → add declaration near other signal declarations

**Fix template:**
```diff
  // Signal declarations
  wire [7:0] data_in;
+ reg  [7:0] my_signal;  // <- add missing declaration
```

### VLOG-133: Net on LHS of Procedural Assignment

```
ERROR: [Synth 8-133] net 'result' can not be used in left-hand side of procedural assignment [file.v:50]
```

**Steps:**
1. Read declaration of `result` — confirm it's `wire`
2. Change to `reg` or `logic` (SystemVerilog)
3. If ANSI port style, change `output wire result` → `output reg result`

**Fix template:**
```diff
- output wire [7:0] result,   // <- wire cannot be procedurally assigned
+ output reg  [7:0] result,   // <- change to reg for always block assignment
```

### VLOG-134: Variable on LHS of Continuous Assignment

```
ERROR: [Synth 8-134] variable 'data_out' can not be used in left-hand side of continuous assignment [file.v:30]
```

**Steps:**
1. Read declaration of `data_out` — confirm it's `reg`/`logic`
2. Option A: Change to `wire` if used with `assign`
3. Option B: Move assignment into `always` block if sequential

### VLOG-564: Incomplete Sensitivity List

```
WARNING: [Synth 8-564] referenced signal 'sel' should be on the sensitivity list [file.v:80]
```

**Steps:**
1. Read the always block at line 80
2. Find the `@(...)` event control
3. Option A (recommended): Replace with `@(*)` or `always_comb`
4. Option B: Add the specific missing signal

**Fix template:**
```diff
- always @(a, b)          // <- missing 'sel' from sensitivity list
+ always @(a, b, sel)     // <- add missing signal
```
Or better:
```diff
- always @(a, b)          // <- incomplete sensitivity list
+ always @(*)             // <- automatic sensitivity list
```

### VLOG-566: Inferring Latch

```
WARNING: [Synth 8-566] inferring latch for variable 'state_reg' [file.v:100]
```

**Steps:**
1. Read the always block containing line 100
2. Find incomplete `if`/`case` branches (missing `else`/`default`)
3. Add the missing branch to make logic fully specified

**Fix template (case):**
```diff
  case (state)
    IDLE:  next_state = RUN;
    RUN:   next_state = DONE;
    DONE:  next_state = IDLE;
+   default: next_state = IDLE;  // <- prevent latch inference
  endcase
```

**Fix template (if):**
```diff
  if (enable)
    data_out = data_in;
+ else
+   data_out = '0;             // <- prevent latch inference
```

### VLOG-637: Dual Driver (Continuous + Procedural)

```
CRITICAL WARNING: [Synth 8-637] variable 'data' cannot be written by both continuous and procedural assignments [file.v:55]
```

**Steps:**
1. Search file for all assignments to the named variable
2. Identify which is `assign` (continuous) vs `always` block (procedural)
3. Remove one — typically convert `assign` to procedural or vice versa

### VHDL-758: Signal Not in Sensitivity List

```
WARNING: [Synth 8-758] signal 'sel' is read in the process but is not in the sensitivity list [file.vhd:80]
```

**Steps:**
1. Read the process at line 80
2. Find the sensitivity list
3. Option A: Add the missing signal
4. Option B (VHDL-2008): Use `process(all)` — requires `-vhdl2008` flag in project

**Fix template:**
```diff
- process(a, b)           -- missing 'sel' from sensitivity list
+ process(a, b, sel)      -- add missing signal
```

### VHDL-747: Missing Case Choices

```
ERROR: [Synth 8-747] missing choice(s) in case statement [file.vhd:120]
```

**Steps:**
1. Read the case statement at line 120
2. Determine the type of the case expression
3. Identify which values are not covered
4. Add `when others =>` clause

**Fix template:**
```diff
  case state is
    when IDLE => next_state <= RUN;
    when RUN  => next_state <= DONE;
+   when others => next_state <= IDLE;  -- cover all remaining values
  end case;
```

### VHDL-759: Width Mismatch in Assignment

```
ERROR: [Synth 8-759] width mismatch in assignment; target has 8 bits, source has 16 bits [file.vhd:45]
```

**Steps:**
1. Read line 45 for the assignment
2. Read declarations of both source and target signals
3. Option A: Resize source with `resize()` or slice
4. Option B: Widen target declaration

### VHDL-833: Unknown Identifier

```
ERROR: [Synth 8-833] Unknown identifier my_func [file.vhd:60]
```

**Steps:**
1. Search workspace for `my_func` definition
2. If found in a package → add `use work.pkg_name.all;`
3. If found in another library → add `library lib; use lib.pkg.all;`
4. If typo → fix the name
5. If missing → report as "declaration needed"

---

## Cascading Error Detection

Some errors cause chains of follow-on messages. Identify and mark cascading errors:

| Root Cause | Cascading Messages |
|------------|-------------------|
| VLOG-128 (undeclared) | Multiple VLOG-546 (unresolved), VLOG-576 (type mismatch) |
| VLOG-624 (undeclared type) | Multiple VLOG-128 (undeclared variable of that type) |
| VHDL-768 (unit not found) | Multiple VHDL-833 (unknown identifier from that unit) |
| VHDL-773 (missing body) | Multiple VHDL-833 (identifiers declared in the body) |
| VLOG-404 (module not found) | VLOG-402 (failed synthesizing) for parent |
| VLOG-109 (include not found) | Multiple parser errors in files that depend on the header |

**Strategy:** Fix root causes first. After applying root cause fixes, many cascading
messages will resolve automatically. In the report, group cascading messages under
their root cause and note: "These N messages are likely caused by the above error
and should resolve after fixing it."
