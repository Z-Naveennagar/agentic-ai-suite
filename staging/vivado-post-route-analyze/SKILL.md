---
name: vivado-post-route-analyze
description: Analyzes a post-route Vivado design checkpoint, classifies failing timing paths, and highlights one representative critical path per violation category in a distinct color in the Vivado GUI. Designed for tutorials and design reviews where visual explanation of timing issues is key.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Post-Route DCP Analysis

Two-phase analysis-only flow executed via `vivado-mcp:vivado_execute`.

```
Task Progress:
- [ ] Phase 1: Analyze post-route DCP & classify violations
- [ ] Phase 2: Highlight representative critical paths in Vivado GUI
```

---

## Phase 1 — Analyze

### 1.1 Open design

```tcl
open_run impl_1
# Non-project: open_checkpoint <path_to_routed.dcp>
```

VERIFY: Design is routed before proceeding.

### 1.2 Capture baseline metrics

```tcl
set baseline_wns  [get_property SLACK [get_timing_paths -max_paths 1]]
set paths_neg [get_timing_paths -max_paths 1000 -slack_lesser_than 0]
set baseline_fail [llength $paths_neg]
set baseline_tns 0.0
foreach p $paths_neg {
    set baseline_tns [expr {$baseline_tns + [get_property SLACK $p]}]
}
```

Store: `baseline_wns`, `baseline_tns`, `baseline_fail`.

EARLY EXIT: If `baseline_wns` >= 0 → report "No timing violations — design meets timing" and stop.

### 1.3 Collect reports & classify

Read [reference/classification.md](reference/classification.md) for detailed Tcl and classification rules.

Output: a list of failing paths, each tagged with exactly one category:
- **CDC** — Clock Domain Crossing
- **SLR Crossing** — Super Logic Region boundary crossings
- **High Fanout** — nets driving too many loads
- **Long Logic** — excessive combinational logic levels
- **Unclassified** — paths matching no category (flagged for manual review)

### 1.4 Select representative paths

For each category that has at least one failing path, select the **single worst-slack path** as the representative. Store these representative paths (Tcl timing path objects or their startpoint/endpoint names) for Phase 2.

### 1.5 Present analysis summary

Present to the user:
- **Baseline metrics**: WNS, TNS, total failing path count
- **DONT_TOUCH census**: sequential, combinational, and net counts (from classification Step 1.5). Flag if sequential DT cells bound long-logic paths — these block `opt_design` remap.
- **Classification summary table**: category, path count, worst slack, representative path (startpoint → endpoint)
- **Unclassified paths** flagged for attention (if any)
- **Color legend** that will be used in Phase 2 highlighting

| Category | Color | RGB |
|---|---|---|
| CDC | **Red** | `#FF0000` |
| SLR Crossing | **Blue** | `#0000FF` |
| High Fanout | **Orange** | `#FF8C00` |
| Long Logic | **Green** | `#00AA00` |
| Unclassified | **Purple** | `#8B008B` |

Then ask: **"Proceed to highlight these representative paths in the Vivado GUI?"**

Do NOT continue to Phase 2 until the user confirms.

---

## Phase 2 — Highlight Critical Paths (Interactive, One Category at a Time)

Read [reference/highlighting.md](reference/highlighting.md) for the detailed Tcl highlighting procedure.

Phase 2 walks the user through each violation category **one at a time**.
The order follows classification priority: CDC → SLR Crossing → High Fanout → Long Logic → Unclassified.
Skip any category that has zero failing paths.

### 2.1 Clear previous marks

Remove any existing highlight marks to start clean.

### 2.2 Iterative category walkthrough

For each category with a representative path, execute this loop:

#### Step A — Clear prior category highlights

Before highlighting the new category, clear the previous category's highlights so the view is uncluttered:

```tcl
catch {unhighlight_objects [get_highlighted_objects]}
catch {unmark_objects [get_marked_objects]}
```

Exception: On the **first** category, this is the initial clean (same as 2.1).

#### Step B — Highlight this category's representative path

Use `highlight_objects` and `mark_objects` with the category-specific color from the color map. Then fit the view to the highlighted objects.

#### Step C — Report the path

Show `report_timing` output for this representative path so the user can correlate the visual with timing data.

#### Step D — Present category summary and wait

Present to the user:
- **Category name** and **color** being shown
- **Path count** in this category and **worst slack**
- **Representative path**: startpoint → endpoint, slack, logic levels, route delay %
- Brief explanation of **why** this path type violates timing
- Brief description of the **fix** approach (reference only — do not apply)

Then:
- If more categories remain, ask: **"Proceed to next category: \<next_category_name\> (\<color\>)?"**
- If this is the last category, ask: **"All categories reviewed. Show all paths highlighted together, or clear marks?"**

Do NOT proceed to the next category until the user confirms.

### 2.3 Final composite view (optional)

If the user requests it after reviewing all categories individually, re-highlight **all** representative paths together (one per category, each with its own color) and fit the view. This gives the combined overview.

### 2.4 Present final summary

Present to the user:
- Confirmation of which categories were reviewed
- The complete color legend for reference
- How to clear marks when done: `unhighlight_objects [get_highlighted_objects]`
- Suggestion: use the `timing-closure` skill to generate fixes for these violations

---

## Guardrails

1. **Analysis only** — this skill does NOT generate constraints or rerun implementation. For fixes, use the `timing-closure` skill.
2. **No placeholders** — all Tcl commands must use real design names from the actual checkpoint.
3. **One path per category** — highlight exactly one representative (worst-slack) path per category for clarity.
4. **Color consistency** — always use the color map defined above so tutorials are reproducible.
5. **Non-destructive** — highlighting and marking do not modify the design. They are purely visual annotations.
6. **Routed design required** — the design must be fully routed. Do not attempt on unrouted checkpoints.
````
