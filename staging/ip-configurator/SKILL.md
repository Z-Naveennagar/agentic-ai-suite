---
name: ip-configurator
description: "Use this skill for configuring ANY Vivado IP block via natural language. Trigger whenever the user asks to configure, customize, parameterize, or set up an IP core — including AXI peripherals, processing systems (Zynq PS, Versal CIPS), memory controllers, DSP blocks, clocking, resets, DMA, interconnects, or any IP with CONFIG.* properties. Also trigger when the user provides a high-level description of desired IP behavior and expects the correct set_property -dict to be generated. This skill uses a two-tier approach: Tier 1 builds the configuration from documentation, Tier 2 recovers from errors using Vivado's own feedback."
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# IP Configurator — Doc-Driven Configuration with Error Recovery

## Overview

This skill configures Vivado IP blocks from natural-language prompts using a two-tier approach
that treats Vivado as the source of truth. It does NOT rely on pre-built parameter databases
or exhaustive JSON dumps of IP configuration spaces.

**Tier 1 — Doc-Driven First Attempt:**
1. Search AMD documentation for the IP's configuration parameters
2. Build a `set_property -dict` from the docs
3. Execute it via `vivado_execute`

**Tier 2 — Error-Driven Recovery (only if Tier 1 fails):**
1. Parse the error message from the failed `set_property -dict`
2. Search docs for the specific parameters/constraints mentioned in the error
3. Build a corrected `-dict` and retry

Key principle: `set_property -dict` is **atomic for hard errors** — if it throws, no
parameters are changed, and the error messages are rich and specific.

**Caveat (critical):** In IP Integrator (BD) mode, an *unknown* CONFIG parameter does
**not** throw. Vivado emits a non-fatal `CRITICAL WARNING [BD 41-1276] ... does not exist`
(or `[IP_Flow 19-7090] Invalid parameter ... Ignoring`), `catch` returns 0, and the script
would falsely report success. Therefore Tier 1 must **verify** that the parameters actually
took effect (see Step 3, Phase 3 verification) and the agent must **scan the execute output**
for these warning patterns before declaring SUCCESS — never trust the `SUCCESS:` line alone.

## Operating Modes

This skill runs in one of two modes. Choose the mode at the start of the session and keep it.

| Mode | When | Behavior |
|---|---|---|
| `unattended` (default) | Nobody is available to answer a question — a scripted, CI, or otherwise automated run | Deterministic and **silent**: never ask; make the documented best choice and record the assumption in the Step 1.5 ledger. Minimize MCP calls. |
| `interactive` | A human is in the loop, turn by turn, building a real design | May **ask clickable clarifying questions** when doc search is inconclusive, and proactively uses Block Automation / Configurable Example Designs to flesh out the design. |

If the mode is not stated, assume `unattended`: a question nobody answers stalls the run
until it times out, whereas a documented best choice recorded in the ledger is always
recoverable. Switch to `interactive` only when the user has actually been conversing with
you turn by turn. Steps below are tagged **(both)**, **(interactive)**, or **(unattended)**
where the behavior differs. Everything not tagged applies to both.

## Always report coverage (REQUIRED, both modes)

You MUST tell the user, in plain language, whether the IP was **fully parameterized** from
the prompt — and if not, **exactly which part(s) of the prompt could not be applied, and why**.
Never silently grade `partial` / `creation_only` / `negative`.

Drive this from the Step 1.5 requirement ledger. Every atomic requirement ends in one outcome:
- `applied` — set and verified (stuck + intent realized)
- `default` — already correct by default (`value_src=default`, acceptable)
- `unapplied:<reason>` — could not be parameterized; `<reason>` is one of
  `runtime-register-only`, `integration-derived`, `gated-no-enabler`, `not-a-config-param`,
  `value-out-of-range`, `wrong-ip-for-capability`.

Emit the coverage report whenever the result is not fully applied:

```tcl
puts [ipcfg::coverage_report $ledger]   ;# COVERAGE:FULL | COVERAGE:PARTIAL + the unapplied list
```

Then say to the user, verbatim about the gaps: "I could **not** fully parameterize `<IP>` from
the prompt. Applied: <list>. Could NOT apply: '<the exact prompt phrase>' because <reason>."
Quote the actual prompt fragment for each gap — do not paraphrase it away.

## MCP Tools Used

Only THREE tools are needed:

| Tool | Purpose | When |
|------|---------|------|
| `vivado_doc_search` | Find IP parameters, valid values, dependencies | Tier 1 (always), Tier 2 (on error) |
| `vivado_execute` | Run `set_property -dict` and read-back commands | Both tiers |
| `vivado_log_messages` | Additional diagnostics if error string is ambiguous | Tier 2 (rare) |

## Workflow

### Step 0: Part resolution (guarded — before anything else)

Many IPs only exist on specific device families. **A part swap is destructive to a
design-in-progress**: existing IP may be incompatible with the new part, will need
upgrading, and may then mismatch the original prompts. So treat swapping as **opt-in and
last-resort** *while other cells exist*. On an empty or isolated BD — a single-IP task — a
swap is cheap, guard-approved and **expected**; "last resort" is never a licence to build the
wrong IP instead:

1. **Check availability on the current part first** — `ipcfg::ip_availability {<candidates>}`
   (**mandatory before any create**, see Step 0a′). If the IP is `AVAILABLE`, do **not** swap.
2. **Only if `WRONG_PART`**, consider a swap. `ipcfg::ensure_part <part>` is **guarded**: if
   other `bd_cells` already exist it returns `WARN:SWAP_BLOCKED:...` instead of swapping.
   - **(interactive)** On `WARN:SWAP_BLOCKED`, **ask the user** (clickable) whether to swap,
     warning that existing IP may need upgrading and could mismatch their intent. Only call
     `ipcfg::ensure_part <part> 1` (force) after they confirm.
   - **(unattended)** When the BD holds no other cells the guard passes on its own and the
     swap proceeds; restore the part in cleanup. Never force past `WARN:SWAP_BLOCKED` with
     no human to confirm — report it as `unapplied:wrong-ip-for-capability` instead.
3. Never swap silently mid-design.

**Step 0a — Doc search for device family (combined with parameter search):**

Include device/family keywords in the Tier 1 doc search so a single call covers both
part compatibility and CONFIG parameters:

```
vivado_doc_search("<IP name> supported devices configuration parameters")
```

From the results, extract:
- Which device families support this IP (Zynq-7000, Zynq US+, UltraScale+, Versal, etc.)
- The CONFIG.* property names (used in Step 3)

**Step 0a′ — MANDATORY availability gate (before any `create_bd_cell`):**

Run the **candidate shortlist** — every IP you are choosing between, not the one you already
favour — through the gate. Build the shortlist from the prompt's **function words** as a catalog
**glob**, which the proc expands against this release, so the shortlist is discovered rather than
pre-committed to the first name that came to mind:

```tcl
puts [ipcfg::ip_availability {*clk*wiz*}]     ;# prompt says "clocking wizard"
# IPAVAIL: part=xc2ve3558-sfva1440-2MP-e-S \
#   clk_wizard=WRONG_PART:xilinx.com:ip:clk_wizard:1.0:parts={xcvc1502-... xcvc1902-viva1596-2MP-e-S ...}:devices=63 \
#   clkx5_wiz=AVAILABLE:xilinx.com:ip:clkx5_wiz:1.0
```

**Passing ONE pre-chosen name is the misuse this gate exists to prevent** — it can only confirm
a name you already picked, so an IP that is `WRONG_PART` never gets compared against the one that
happens to work. The proc says so (`SHORTLIST_OF_1:validator-only-call:...`); when you see that,
re-run with a glob before creating anything. A shortlist is not "the name plus a rationale"; it
is every catalog IP whose name matches the function you were asked for.

This is **not** optional and **not** replaceable by `ipcfg::vlnv_ok`. `get_ipdefs` (and therefore
`vlnv_ok`) lists IPs the current part **cannot instantiate**: on 2026.1/`xc2ve3558`, `vlnv_ok
xilinx.com:ip:clk_wizard` returns **1** and `create_bd_cell` then fails with
`[BD 5-683] ... not supported for the current part`. Worse, that failure is **not recoverable in
Tier 2**: `catch` sees only `[Common 17-39] 'create_bd_cell' failed due to earlier errors`, and
the `[BD 5-683]` naming the cause reaches only the log. Predict it here; do not discover it there.

> **FIRST, check for `VARIANT_OF:` — one IP split across device generations.**
> A release can ship the *same* IP twice under different catalog names, each covering a different
> device generation, with **identical `DISPLAY_NAME`** and disjoint `SUPPORTED_PARTS`. 2026.1 ships
> "Clocking Wizard" three times: `clk_wiz` (7-series/UltraScale), `clk_wizard` (Versal Gen1 —
> **0** `xc2ve*` parts) and `clkx5_wiz` (Versal Gen2 — **375** `xc2ve*` parts and none of Gen1's).
> When the gate reports `VARIANT_OF:{a~b}`, the `AVAILABLE` one **is** the documented IP for this
> device: **use it and do not swap.** Swapping would move to an older device generation just to
> reach an older edition of the same core. From the outside this pair looks identical to the
> wrong-IP substitution the next rule forbids, which is why the gate distinguishes them for you
> instead of leaving it to judgement.
>
> **THE SELECTION RULE — for a `SELECT_RULE:` verdict (different IPs, not variants).**
> **Choose the IP by documented function FIRST** (PG321 "Versal Clocking Wizard" → `clk_wizard`).
> A `WRONG_PART` verdict is a reason to consider a **guarded part swap**. It is **NEVER** a reason
> to substitute a *different* IP that happens to be `AVAILABLE` on the current part.
> Concretely: on `xc2ve3558`, `clk_wizard` is `WRONG_PART` while the similarly-named `clkx5_wiz`
> is `AVAILABLE`. Picking `clkx5_wiz` because it creates without complaint is the **wrong IP**,
> silently — the design builds, configures and verifies clean, so nothing ever errors. Swap the
> part instead.
>
> When the gate reports a `WRONG_PART` **and** an `AVAILABLE` candidate together it says
> `SELECT_RULE:...`, because that pair is the one case where a correct shortlist still leads to the
> wrong IP. On that signal, the choice is **not yours to make on availability**: resolve it from
> documentation (`vivado_doc_search "<function> supported devices"`, cite the PG) and pick the IP
> the doc names for the requested function. "The other one was already available" is never a
> reason, and neither is name similarity to the prompt's wording.
>
> **A `WRONG_PART` IP is not "unavailable to you" — it is one part swap away, and that swap is the
> sanctioned path here, not a last resort.** Do not conclude "the documented IP is `clk_wizard`,
> but it is not supported on this part, therefore I must use the available one." That reasoning
> ends in the wrong IP every time. The correct continuation is: "the documented IP is `clk_wizard`,
> it is `WRONG_PART` here, **so I swap to one of the parts the gate listed** and use it."
> `ipcfg::ensure_part` proceeds on its own when the BD holds no other cells (the usual case for a
> single-IP task), so no confirmation is needed; restore the part in cleanup.
>
> A `WRONG_PART` verdict is **NOT** a Step 0d negative. Step 0d is for an IP whose *capability
> envelope* cannot meet the request (`axi_ethernet` asked for 25G). This is a **device** mismatch
> with a mechanical fix, so `fidelity: negative` / `unapplied:wrong-ip-for-capability` is the wrong
> outcome — swapping is available and expected.
>
> **After swapping, do NOT restore the part while the cell still exists.** The design is graded
> from a read-back taken *after* you finish, and the original part cannot hold a cell that needed
> the swap — restoring drops it, so a run that swapped, built and configured perfectly reads back
> as *nothing built*. Either leave the part swapped (the suite resets the workspace afterwards) or
> delete the cell first via `ipcfg::cleanup <cell> <orig_part>`, which orders it correctly.
> `ipcfg::restore_part` now refuses with `WARN:RESTORE_BLOCKED:...` rather than destroying your
> work silently.

Verdicts and the required response:

| Verdict | Meaning | What to do |
|---|---|---|
| `AVAILABLE:<vlnv>` | Instantiable on this part | Use it. Do **not** swap |
| `WRONG_PART:<vlnv>:parts={...}:devices=<n>` | In the catalog; this part can't instantiate it | Pick a part from `parts={...}` (Step 0b's map may name a preferred device — cross-reference it), then **guarded** `ipcfg::ensure_part`. Never substitute another IP |
| `ABSENT:near={...}` | Not in this release at all (renamed/dropped, e.g. 2026.1 `ps11`) | Re-identify from `near={...}` — a swap cannot help |
| `UNKNOWN:<vlnv>` | ipdef publishes no `SUPPORTED_PARTS` | Proceed and let the create decide. Reported honestly rather than guessed, so it never triggers a needless swap |
| `NO_CATALOG_MATCH` | Your glob matched nothing | Broaden it (`*clk*` before `*clk*wiz*`) — do not fall back to guessing a name |
| `SHORTLIST_OF_1:...` | You passed one name, so nothing was compared | Re-run with a glob **before** creating anything |
| `VARIANT_OF:{a~b}` | Same `DISPLAY_NAME`: one IP split by device generation | Use the `AVAILABLE` one. **Do not swap** — `b` *is* this device's edition of `a` |
| `SELECT_RULE:...` | A `WRONG_PART` IP sits beside a genuinely **different** `AVAILABLE` one | Choose by documentation, then swap the part if the documented one is `WRONG_PART` |

Before a destructive swap, confirm the target actually helps — the same proc takes a prospective
part, so this costs one line and no swap:

```tcl
puts [ipcfg::ip_availability {clk_wizard} xcvc1902-vsva2197-2MP-e-S]
# IPAVAIL: part=xcvc1902-vsva2197-2MP-e-S clk_wizard=AVAILABLE:xilinx.com:ip:clk_wizard:1.0
```

**Step 0b — Determine if a part swap is needed:**

**Step 0a′'s `parts={...}` is the primary answer** — it is read live from the ipdef's own
`SUPPORTED_PARTS`, so it cannot go stale against a release. The map below is a **secondary**
source: use it to *prefer* one device when Step 0a′ lists several (its entries are the
representatives the rest of this skill is validated on), and as a fallback when Step 0a′
returned `UNKNOWN`. Prefer doc-search results when they name a specific family.

Static fallback map (IP -> required part):

| IP | Required Part | Why |
|---|---|---|
| `processing_system7` | `xc7z020clg484-1` | Zynq-7000 PS |
| `clk_wizard` | `xcvc1902-vsva2197-2MP-e-S` | Versal Clocking Wizard (PG321) — `Not-Supported` on `xc2ve3(.*)` |
| `versal_cips` | `xcvc1902-vsva2197-2MP-e-S` | Versal CIPS |
| `axi_noc` | `xcvc1902-vsva2197-2MP-e-S` | Versal NoC |
| `mrmac` | `xcvc1902-vsva2197-2MP-e-S` | Versal Multi-Rate MAC |
| `xdma` | `xcvu9p-flga2104-2L-e` | Needs GT quads (Virtex US+) |
| `cmac_usplus` | `xcvu9p-flga2104-2L-e` | 100G needs GT quads |
| `gt_quad_base` | `xcvc1902-vsva2197-2MP-e-S` | Versal GT Quad IP |
| `hbm` | `xcvu37p-fsvh2892-2L-e` | HBM-equipped Virtex US+ |
| `rfdc` | `xczu28dr-ffvg1517-2-e` | RFSoC |
| `axi_ethernet` (10G/25G) | `xcvu9p-flga2104-2L-e` | 10G+ needs GT |

**Step 0c — Part swap TCL (inline in the same script):**

When a swap is actually warranted (Step 0 guard passed, or user-confirmed in interactive mode),
it is embedded at the top of the configuration TCL via the guarded `ipcfg::ensure_part`
(pass `1` to force only after confirmation), and restored after cleanup. See the template
in Step 3.

**Step 0d — Capability pre-check (IP vs. intent):**

> **Does NOT apply to a Step 0a′ `WRONG_PART` verdict.** This step is about a **capability**
> limit — the IP is right but the *value* is outside its envelope. `WRONG_PART` is a **device**
> mismatch: the IP does what was asked, just not on this part, and the swap fixes it. Do not
> route a `WRONG_PART` verdict here, do not grade it `negative`, and above all do not substitute
> a different IP that happens to be available. Swap the part and use the documented IP.

Before building the dict, sanity-check that the chosen IP can actually deliver the
requested capability. Many prompts name a feature that belongs to a *different* IP, and
the BD will silently ignore the unsupported settings rather than error clearly. When the
doc search shows the requested rate/interface/mode is outside the IP's envelope, do **not**
attempt a doomed config — instead **resolve it as a negative**, exactly like a
`VALUE_OUT_OF_RANGE` recovery:

1. Apply the **closest valid** setting the named IP *does* support (e.g. on `axi_ethernet`,
   fall back to `1000BaseX`/`SGMII` when 10G/25G was requested).
2. Grade `negative`, and in `fidelity_note` state both the IP's documented limit **and** the
   correct alternative IP for the requested capability.
3. This is a **resolved** outcome (`tier2_success: true`), not an unrecovered failure — a
   provably-impossible-on-the-named-IP request is a legitimate negative, never a fall-through
   fail. (If the request becomes impossible only via a Vivado error rather than the doc, the
   same resolution applies once the `VALUE_OUT_OF_RANGE`/`PARAM_NOT_FOUND` error confirms it.)

> Note: this path keeps fidelity to the *named* IP. Substituting a different IP to deliver
> the capability (e.g. `axi_ethernet` → `xxv_ethernet`) is intentionally **out of scope** —
> it would change the IP the user asked for. Only do that if the user explicitly asks to
> "use whatever IP achieves X."

General signals that the prompt targets the wrong IP:
- A line rate / data rate above the IP's documented maximum (escalate to the faster IP).
- An interface the IP doesn't expose in BD (e.g. an AXI4 memory-mapped interface on an IP
  whose doc lists only a "Native" interface — that needs a separate controller/bridge IP).
- A mode named as if it were a `CONFIG` enum but documented as a separate IP or domain.

The mapping of which IP provides a capability comes from the doc search, not from a static
table — let the documentation name the right IP, then grade `negative` with that name in
`fidelity_note`.

### Step 1: Parse the intent

Extract from the user's prompt:
- **IP type** — which IP core (e.g., AXI GPIO, AXI DMA, Zynq PS, MIPI CSI-2 RX)
- **Key requirements** — the functional parameters (width, channels, modes, protocols)
- **Cell name** — if specified, otherwise use a sensible default

**A capability may live in a standalone IP OR be integrated into a larger system IP.**
The same feature can be delivered either by a dedicated IP or by a sub-block of a
processing-system / platform IP, configured through a nested `*_CONFIG` dictionary. Let doc
search name where the capability lives; when both paths exist, prefer the one the
surrounding design / example design actually uses. Picking the standalone IP when the
device delivers the feature inside its system IP (or vice-versa) is an
**`unapplied:wrong-ip-for-capability`** outcome — keep the identification doc-grounded, not
name-based.

**When to ask the user (interactive mode):** If `vivado_doc_search` is inconclusive **and** the
unknown materially changes the IP choice or the configuration (e.g. which IP/sub-block
delivers a capability, or an ambiguous requirement), ask a short **clickable** question
rather than guessing or emitting a vague/formulaic answer. In **unattended** mode, never ask
— make the documented deterministic choice and record the assumption in the ledger.

### Step 1.5: Requirement ledger (decompose the prompt)

Before any config, decompose the prompt into a list of **atomic requirements** — one
per named feature, toggle, mode, count, width, rate, or protocol the user asked for.
Carry this ledger through Tier 1 and Tier 2 as a coverage contract:

| Requirement (from prompt) | CONFIG param | Doc evidence (why this param) | Expected observable change |
|---|---|---|---|
| "user-data-type filtering on" | `CONFIG.<X>` | doc line stating X does this | default 0 -> 1 |
| "2 channels" | `CONFIG.<Y>` | doc line stating Y is channel count | default 1 -> 2 |

Rules:
- **Every requirement must map to a specific CONFIG param with a doc citation.** A
  requirement with no mapped param is an *uncovered* requirement — never grade `full`
  while any requirement is uncovered.
- A compound noun phrase is often **multiple** requirements (e.g. "dual memory
  controller with discrete components" = controller-count *and* component-type). Split
  them; a single param rarely covers a compound phrase.
- The "Expected observable change" column feeds the Step 3 intent audit — record the
  default you expect to move away from, so a no-op (value already at the target by
  default) is detectable.

### Step 2: Doc search (Tier 1)

**Consult the learned cache FIRST (0 MCP calls).** Before any doc search, check whether a
prior run already discovered where this feature lives:
```tcl
set hit [ipcfg::cache_get <ip> "<feature phrase>"]   ;# "" on miss
```
On a **hit**, you get the `param`, `shape`, `enabler`, and `value_src` that were earned in a
previous run. Do a cheap `get_property` existence re-verify (the param still exists for this
IP version), then go straight to applying your value — skip the doc search. On a **miss**,
fall through to the doc search below; once you have *confirmed* a mapping (it stuck and
`verify_intent`/`audit_intent` passed), **write it back**:
```tcl
ipcfg::cache_put <ip> "<feature phrase>" CONFIG.<NAME> <scalar|comma-list|nested> \
                 <enabler_param|null> <user|default> "<doc citation>" <ip_version>
```
This kills the run-to-run "found-then-lost" variance and cuts repeat doc searches. The cache
stores **discovery facts only — never the prompt's expected value** (there is no value field;
see `cache/README.md`), so it is safe to consult and populate during a blind run.

Call `vivado_doc_search` with a targeted query. Combine part-family and parameter
discovery into a single call when possible:

```
vivado_doc_search("<IP name> supported devices CONFIG parameters <key feature>")
```

From the results, identify:
- Which device families support this IP (feeds Step 0b)
- The correct CONFIG.* property names
- Valid values and ranges
- Any noted dependencies between parameters

**Doc-grounded mapping (anti-synonym guard) — required for every requirement.**
Pick a parameter because its *documented description* matches the feature's **semantics**,
NOT because the parameter **name** looks related. Param names routinely share keywords
while implementing different functions, so name pattern-matching silently picks the wrong
one (it will set fine and stick, producing a false success that Tier 2 never sees).

- When several candidate params share a keyword from the prompt, read each candidate's
  doc description and choose the one whose description states the requested function.
- Record the deciding doc line in the ledger's "Doc evidence" column — if you cannot cite
  why a param implements the requirement, you have not grounded it yet; search again.
- Illustrative (do not generalize the specific names): a phrase like "user-data-type
  filtering" can collide with distinct params for "embedded non-image data", a "video
  format / ISP bridge", and an actual "user-data-type filter" — only one matches the
  intent. Disambiguate by description, not by which name contains "data" or "filter".
- **Map to the COMPLETE matching set, not the first match.** A single requirement is often
  realized by *several* sibling params, and missing one silently under-configures the IP.
  Enumerate the full neighborhood for the feature keyword with the scratch-cell introspection
  helper, then doc-grant each candidate:
  ```tcl
  puts [ipcfg::discover_params <vlnv> <keyword>]   ;# DISCOVER:CONFIG.<...> CONFIG.<...> ...
  ```
  Validated: `ipcfg::discover_params xilinx.com:ip:mipi_csi2_rx_subsystem lane` returns BOTH
  `CONFIG.CMN_NUM_LANES` **and** `CONFIG.C_DPHY_LANES` (plus active-lane siblings) — a "N
  lanes" requirement must set the ones the docs say apply, not just whichever name you hit
  first. Write confirmed discoveries to the learned cache (`ipcfg::cache_put`).

  **MANDATORY — discover before you write. Two hard rules, no exceptions:**

  1. **Never issue a `set_property` for a parameter whose name you have not just read off
     the design.** A name from documentation, from memory, or from a prompt's phrasing is a
     hypothesis, not a parameter. Writing first and correcting from the error is the single
     largest source of wrong configurations and of run-to-run variance, and it is not
     permitted here.
  2. **Never take the IP's identity from documentation — resolve it against the catalog.**
     IP names change between releases and a stale name fails with nothing to correct it:
     on 2026.1 `xilinx.com:ip:ps11:1.0` is **absent from the catalog entirely** (the PS
     family is `ps11_vip`, `ps_wizard`, `psx_vip`, `psx_wizard`), so a 2025.2-era guess
     cannot be recovered by retrying.

  **The default path is ONE call.** `ipcfg::configure_feature` performs catalog identity →
  discovery → shape resolution → apply → verify internally, and consults/updates the learned
  cache. Use it unless a requirement genuinely cannot be expressed through it:

  ```tcl
  puts [ipcfg::configure_feature <cell> <ip-name-or-vlnv> <feature-word> <intent-dict>]
  # CF:OK shape=NESTED vlnv=xilinx.com:ip:ps_wizard:1.0 src=discovery applied={...} verified=all
  ```

  You supply *intent* (the feature word from the prompt, and the values you want). It supplies
  the *procedure*, so the same prompt takes the same path every run. `<feature-word>` is
  synonym-broadened automatically (`CAN-FD` → `CAN_FD` → `CANFD` → `CANF` → `CAN`), which is
  why a prompt word reaches `PS_CAN1_PERIPHERAL` without you guessing the spelling. Intent
  keys may be partial; an ambiguous key is **reported, never guessed**
  (`CAN1` → `AMBIGUOUS:{PS_CAN1_CLK PS_CAN1_PERIPHERAL}`), and you then re-issue with the
  precise name.

  **When you need the pieces separately** (multi-pass IPs, gated params, range probing), the
  same discovery is available directly — still before any write:

  ```tcl
  puts [ipcfg::ip_availability {<candidates>}] ;# IPAVAIL: AVAILABLE | WRONG_PART:...:parts={...} | ABSENT | UNKNOWN
  puts [ipcfg::resolve_vlnv <name>]          ;# VLNV:<exact> | VLNV_CANDIDATES:{...} | VLNV_NONE
  puts [ipcfg::find_params <cell> <feature>] ;# FP:FLAT ... | FP:NESTED container=CONFIG.<X> ...
  ```

  `configure_feature` runs the Step 0a′ gate itself (Phase 1b) and returns
  `CF:FAIL:WRONG_PART:...:parts={...}` instead of a create that fails unrecoverably, so the
  single-call path inherits the gate. On that verdict, swap the part and re-issue the same call —
  do not change the IP.

  `find_params` reads the **live BD cell** and reports both the real names and their SHAPE, so
  it is version-agnostic by construction: the same call finds flat `CONFIG.PS_CAN1_PERIPHERAL`
  on a 2025.2 `ps11` and the nested `CONFIG.PS11_CONFIG` sub-key on a 2026.1 `ps_wizard`.

  **Subsystem / PS-class IPs (`ps_wizard`, `versal_cips`, `psx_wizard`) — read the cell, not a
  managed IP.** Their parameters are sub-keys of one dict-valued property, and on 2026.1
  `ps_wizard` is **IPI-only** (`[Ipptcl 7-1663] ... intended for use in IPI only`), so
  `create_ip` fails and every managed-IP path is unavailable: `ipcfg::param_deps` returns
  `PARAM_DEPS_NO_MANAGED_IP` and `ipcfg::discover_params` returns `DISCOVER_IPI_ONLY`. Use
  `ipcfg::find_params` / `ipcfg::cell_dict_keys` on the BD cell instead — one round-trip, no
  172 KB dump. Concretely on 2026.1 `ps_wizard`: 19 top-level `CONFIG.*` props, **no flat
  `CONFIG.PS_CAN*` at all**, and the CAN-FD params living only inside `CONFIG.PS11_CONFIG`
  (the `_INTERNAL` twin holds the ~1315 resolved sub-keys and is derived/read-only — set the
  user-facing param, read either).

  **On Vivado 2026.1+ (VIVADO-23126), native param discovery is still the cheapest path for
  FLAT-param managed IPs.** Gate with `ipcfg::has_native dump_param_deps`. When 1, replace the
  per-IP `vivado_doc_search` with one `ipcfg::param_deps <scratch_ipname>` (dump to file) +
  targeted `ipcfg::param_block` reads — explicit Range/Enabled/Disabled per param, ~87% fewer
  tokens and ~30% fewer MCP round-trips on the rave2 Versal subset. **Always** read targeted
  blocks, never the whole dump (172 KB `ps_wizard` … 665 KB `axi_noc`). `dump_param_deps` does
  NOT carry per-sub-key range/gating, so for the handful of sub-keys a prompt actually touches
  use the **set-and-observe** helpers instead of a doc search: `ipcfg::probe_subkey_range`
  (push an out-of-range sentinel — non-destructive, the customizer auto-restores; run with
  `capture_log=true` and parse the legal set with `ipcfg::range_from_log`, since the
  `is out of range { ... }` text only reaches the log) and `ipcfg::resolve_subkeys` (apply legal
  inputs, read back the resolved `*_INTERNAL` to see what was derived/gated). Both are
  version-INDEPENDENT (customizer feedback, not a 23126 command), so they are the range/gating
  fallback on BOTH 2025.2 and 2026.1.

**Backend resilience:** If `vivado_doc_search` returns a non-JSON / HTML error payload
(e.g. an HTTP 404 page) rather than documentation, treat it as a *backend failure*, not as
"no parameters found." Retry once against the alternate doc-search server if one is
available; if doc search stays unavailable, fall back to **error-feedback-only mode** —
attempt a best-effort dict from the prompt and let Tier 2's Vivado error messages drive the
correction. Never grade a prompt down just because the doc backend was unreachable.

### Step 2.5: Source the helper library (ONCE per session)

All repetitive TCL (part swap, VLNV check, cell creation, dict apply with error
classification, stuck-value verification, value-format introspection, block automation,
stub connections, cleanup) lives in a generic, **IP-agnostic** helper library shipped with
this skill: `lib/ipcfg.tcl`. Source it exactly once per Vivado session, after a block
design is open:

```
vivado_execute("source <skill_dir>/lib/ipcfg.tcl")
```

The helpers contain **no** IP names, VLNVs, or parameter names — every IP-specific value is
passed in by you (discovered from doc search + Vivado feedback). Each proc returns one
parseable line: `SUCCESS:<detail>` or `CONFIGURE_FAIL:<TYPE>:<detail>`.

| Helper | Purpose |
|---|---|
| `ipcfg::configure_feature <cell> <ip> <feature> <intent>` | **THE default path.** Catalog identity → discovery → shape → apply → verify → cache, in ONE call. You pass intent (feature word + values); it fixes the procedure, which is what makes repeat runs identical. Intent keys may be partial; ambiguity is reported, never guessed. → `CF:OK shape=<FLAT\|NESTED> vlnv=<v> src=<discovery\|cache> applied={...} verified=all` \| `CF:PARTIAL ... unresolved={...} bad={...}` \| `CF:FAIL:<TYPE>:<detail>` |
| `ipcfg::find_params <cell> <feature>` | **Unified discovery on the live cell**: finds the real param names AND their SHAPE, checking flat `CONFIG.*` props first, then inside every dict container. Version-agnostic by construction (flat `CONFIG.PS_CAN1_PERIPHERAL` on 2025.2 `ps11`; nested on 2026.1 `ps_wizard`). Synonym-broadened. → `FP:FLAT pattern=<p> n=<k> {...}` \| `FP:NESTED container=CONFIG.<X> ...` \| `FP_NONE`/`FP_ERR` |
| `ipcfg::cell_dict_keys <cell> <dictparam> ?pattern?` | Nested-dict sub-keys read **straight off the BD cell** — no `create_ip`, no dump file. This is the ONLY introspection path for IPI-only subsystem IPs (2026.1 `ps_wizard`). Falls back to `<param>_INTERNAL` when the user param is still empty. → `CDK:<prop> pattern=<p> n=<k> {k v ...}` \| `CDK_NONE` \| `CDK_ERR` |
| `ipcfg::resolve_vlnv <name-or-vlnv>` | **Catalog-grounded IP identity.** Unlike `vlnv_ok` (which only validates a name you already chose) this rescues a name that no longer exists by naming what the release actually ships. → `VLNV:<exact>` \| `VLNV_CANDIDATES:{...}` \| `VLNV_NONE`. On 2026.1, `resolve_vlnv ps11` returns the PS family incl. `ps_wizard` |
| `ipcfg::ensure_part <part> ?force?` | **Guarded** swap (close/reopen bd). Returns `SWAP:old->new`, `NOSWAP:p`, or `WARN:SWAP_BLOCKED:...` when other cells exist; pass `force=1` only after user confirmation |
| `ipcfg::restore_part <orig> ?force?` | Swap back — **guarded in the mirror image**: returns `WARN:RESTORE_BLOCKED:...` when a cell that the original part cannot support would be silently dropped. Delete the cell first (`ipcfg::cleanup <cell> <orig>` orders it correctly) or leave the part swapped |
| `ipcfg::ip_availability {<candidates-or-globs>} ?part? ?maxparts?` | **MANDATORY pre-create part gate** (Step 0a′), and the only proc that helps you *choose*: a three-way verdict per candidate from the ipdef's own `SUPPORTED_PARTS`, which predicts `[BD 5-683]` exactly. Entries may be **catalog globs** (`*clk*wiz*`), expanded against the release, so the shortlist is discovered instead of pre-chosen. → `IPAVAIL: part=<p> <name>=AVAILABLE:<vlnv>` \| `<name>=WRONG_PART:<vlnv>:parts={...}:devices=<n>` \| `<name>=ABSENT:near={...}` \| `<name>=UNKNOWN:<vlnv>` \| `NO_CATALOG_MATCH` \| `SHORTLIST_OF_1:...` (one name = validator misuse; re-run with a glob). Pass a prospective `part` to confirm a swap target **before** swapping. `WRONG_PART` → swap the part, **never** substitute a different IP |
| `ipcfg::vlnv_ok <vlnv_prefix>` | 1/0 — **catalog membership only, NOT part availability.** `get_ipdefs` lists IPs the current part cannot instantiate, so this returns 1 for an IP whose `create_bd_cell` then fails with `[BD 5-683]` (2026.1 `clk_wizard` on `xc2ve3558`). Use `ipcfg::ip_availability` for any availability decision |
| `ipcfg::create_cell <vlnv> <cell>` | Idempotent `create_bd_cell` with error classification |
| `ipcfg::create_cell_cfg <vlnv> <cell> <dict>` | **Preferred:** create **and** configure in ONE call via `create_bd_cell -set_param` (skips init-to-default + separate apply); falls back to create+apply_dict if unsupported |
| `ipcfg::apply_dict <cell> <dict>` | `set_property -dict` with `PARAM_NOT_FOUND/VALUE_OUT_OF_RANGE/READ_ONLY/NOT_SUPPORTED/PARAM_DISABLED` classification (use to add/fix params after `create_cell_cfg`) |
| `ipcfg::reconcile_disabled <cell> <dict>` | For gated/disabled keys: returns `OMIT:{...}` (current value already equals intent — drop them) and `DIFFER:{...}` (real problem — only these need an enabler) |
| `ipcfg::is_system_intent <text>` | Heuristic: does the prompt describe a **subsystem** (integrated MC, PCIe controller, PS PL-clocks/peripherals)? Returns `SYSTEM:{reasons}` or `STANDALONE`. A `SYSTEM` verdict → try automation-first; if no rule + gated params, report integration-derived honestly |
| `ipcfg::rule_for_vlnv <dump> <vlnv>` | Parse a captured `::bd::util_cmd rules dump` to get the Designer-Assistance rule for a cell's VLNV → `RULE:xilinx.com:bd_rule:<short> desc={...}` or `RULE:none` (version-free or full VLNV ok) |
| `ipcfg::apply_automation_harvest <cell> <rule> ?config? ?baseline?` | Apply a rule (id `xilinx.com:bd_rule:<short>` from the dump) and **harvest**: `HARVEST:changed={k old new class ...} new_cells={...}`. Pass the rule's `<config>` options — a bare apply is often a no-op for subsystem features. Now classifies two failures: `CONFIGURE_FAIL:MISSING_AUTOMATION_KEY:<k>` (→ run `automation_config_schema`) and `CONFIGURE_FAIL:NEEDS_BOARD_PRESET:<err>` (→ set `BOARD_PART`/load preset) |
| `ipcfg::automation_config_schema <rule_file>` | Read a rule's `.tcl` (+ sibling `utils.tcl`) and return the **required `-config` keys + default values** so you build a valid options dict instead of failing on `key "<k>" not known` → `SCHEMA:keys={..} defaults={k v ..} file=<path>`. Validated: `ps_wizard`→`{mc_type pl_clocks board_preset ...}`, `visp_ss`→`{mem_map}`, `axi_noc2`→`{mc_type num_mc pl2noc_psx}` |
| `ipcfg::snapshot_all <cell>` | Capture the **entire** `CONFIG.*` dict in one pass (baseline for `config_diff`/harvest) |
| `ipcfg::config_diff <cell> <baseline> ?reqmap?` | Full-config diff after an apply. Requested keys → `EXACT/RESOLVED/REVERTED`; other moved keys → `CHANGED` (IP side effect). Returns `{key old new class ...}` |
| `ipcfg::classify_change <want> <base> <cur> ?validset?` | One-key verdict: `EXACT` / `RESOLVED` (IP snapped to nearest legal value — **not** a miss) / `REVERTED` (snapped to default/elsewhere); `UNCHANGED`/`CHANGED` when `want=""` |
| `ipcfg::discover_params <vlnv> <keyword>` | Scoped introspection on a throwaway `create_ip` cell → `DISCOVER:CONFIG.<...> ...` (the **complete** param neighborhood matching a feature keyword). Keyword is synonym-broadened, so a prompt word no longer misses the params. The one sanctioned `list_property` use; maps a requirement to the full sibling set (e.g. `CMN_NUM_LANES` **and** `C_DPHY_LANES`). Returns `DISCOVER_IPI_ONLY:<vlnv>` for IPI-only IPs (2026.1 `ps_wizard`) — switch to `ipcfg::find_params` on the BD cell |
| `ipcfg::native_caps` / `ipcfg::has_native <feature>` | **Version gate (2026.1+).** Detects, once per session, whether the native VIVADO-23126 commands exist (by **command presence**, not version string — some `2026.1_*` builds report `2025.2.0`). `feature` = `dump_param_deps` \| `can_connect` → `0/1`. All native helpers below return `*_NA` when 0 so you fall back to the reactive path |
| `ipcfg::param_deps <ipname> ?file?` | **2026.1+ fast param discovery.** `::debug::dump_param_deps` (resolved Range/Enabled/Disabled + dependency graph) written to a FILE → `PARAM_DEPS:<file>:<bytes>` or `PARAM_DEPS_NA`. For **flat-param IPs** this REPLACES the per-IP `vivado_doc_search` (measured ~50–72 KB) — confirmed ~87% fewer tokens on the rave2 subset. `ipname` must be a managed-IP instance (`create_ip` first); BD cell names are rejected. Returns `PARAM_DEPS_NO_MANAGED_IP:<name>` when no such managed IP exists — which is the normal case for IPI-only subsystem IPs that `create_ip` cannot build at all (2026.1 `ps_wizard`); use `ipcfg::find_params` on the BD cell instead |
| `ipcfg::param_block <file> <param>` | **Targeted read** of ONE param's block from a `param_deps` dump (Range/Enabled/Disabled/Default). ALWAYS use this — never inline the whole dump (172 KB ps_wizard … 665 KB axi_noc); a blanket read is ~2× worse than 2025.2 |
| `ipcfg::param_dict <file> <dictparam> ?subkey?` | **Nested-dict introspection** for PS/CIPS-class IPs. `dump_param_deps` exposes the real sub-keys only inside one resolved dict value (`ps_wizard` `PS11_CONFIG_INTERNAL` = a ~1315-key flat Tcl dict). `subkey=""`→`PD_KEYS:<all top-level keys>`; else `PD:<k>=<value>`. Recovers sub-key **names + current/default values** with NO doc search. **Limit:** per-sub-key valid-range/gating is NOT in the dump → use the two set-and-observe helpers below |
| `ipcfg::probe_subkey_range <cell> <dictparam> <subkey> ?sentinel?` | **Per-sub-key RANGE via set-and-observe** (fills the gap `dump_param_deps` leaves). Pushes an out-of-range sentinel for ONE sub-key on a BD cell's dict user-param; the customizer rejects it and **auto-restores** (non-destructive). Returns `PSR_OUT_OF_RANGE:<k>` (validated input — the legal set is in the captured log) \| `PSR_NOTVALIDATED` (free-form input, no range) \| `PSR_NOKEY` (derived/ignored, not user-settable) \| `PSR_ERR`. **Run with `capture_log=true`** — the legal-set text ("`is out of range { ... }`") only reaches the message log, NOT `$e`/`errorInfo`. **Version-independent** (2025.2 + 2026.1). Proven on 2026.1 `ps_wizard` (`PS_USE_PMCPL_CLK0 → { 0,1 }`) |
| `ipcfg::range_from_log <console> <subkey>` | **Parser** for the `probe_subkey_range` companion: scan the `capture_log` payload for the sub-key's range line → `RANGE:<k>={ 0,1 }` \| `RANGE_NONE:<k>`. Stateless (same pattern as `find_disabled`/`autofix_apply` taking the console) |
| `ipcfg::resolve_subkeys <cell> <userparam> <override> ?internalparam? ?wantkeys?` | **Gating/derivation via set-and-observe.** Applies a legal `{subkey value ...}` override, reads back the resolved `*_INTERNAL` dict → `RSK:<k v ...>` (or `RSK_KEYS:<n>`). Shows what an input derives/gates (proven: req 250 MHz → `ACT_FREQMHZ 249.997 DIVISOR0 4 SRCSEL NPLL BUF 1`). **Applies a real config change** (snapshot `CONFIG.<userparam>` first if rollback needed). Version-independent |
| `ipcfg::coverage_report <ledger>` | Build the REQUIRED partial-coverage disclosure from the requirement ledger (`COVERAGE:FULL|PARTIAL` + unapplied prompt parts) |
| `ipcfg::snapshot <cell> <keys>` | Capture **baseline default** values BEFORE config (call right after create); returns `{key val ...}` for `verify_intent` |
| `ipcfg::verify_stuck <cell> <dict>` | Returns the list of keys that did **not** take effect (missing **or** value-reverted; handles nested `*_CONFIG` dicts). Empty list = all stuck |
| `ipcfg::check_enablers <cell> <dict>` | **The check `verify_stuck` cannot do.** Finds values that persisted while their enabling flag is still off, so the write is **inert** (`CONFIG.RESET_TYPE ACTIVE_LOW` with `USE_RESET false` reads back fine and produces no reset pin). Returns `INERT:<key>:enabler=<CONFIG.flag>=<value> ...` or `""`. Matched against **this cell's own** parameter names, case-insensitively (`USE_/ENABLE_/EN_/HAS_/INCLUDE_/IS_` and `C_`-prefixed forms, plus `<X>_ENABLE/_EN/_USED`); a flag you set truthily in the same dict is not reported |
| `ipcfg::feature_flags <cell> {<word> ...}` | Intent-side companion: given behavioural nouns from the prompt (`reset locked interrupt sg`), returns the cell's boolean params that enable them with current values — `FLAGS: reset:CONFIG.USE_RESET=false locked:CONFIG.USE_LOCKED=false` or `FLAGS:none`. Use for requests whose whole content **is** the flag ("expose the locked signal"), which name no attribute for `check_enablers` to catch |
| `ipcfg::verify_intent <cell> <reqmap> ?flag_no_change?` | Intent audit: given `{key want baseline ...}`, flags keys that **reverted** OR are **suspect-no-change** (value == default). A value the IP **RESOLVED** to its nearest-legal neighbor (e.g. 600→597.20 MHz) passes — it is **not** flagged. Pass `flag_no_change=0` to return only hard reverts once doc grounding confirms a default legitimately satisfies intent (`value_src=default`). Empty list = intent realized |
| `ipcfg::audit_intent <cell> <reqmap>` | Resolved-aware audit that **reports** buckets: `EXACT:{...} RESOLVED:{k(=cur,want=w) ...} BAD:{...}` — use to feed `coverage_report` so applied-exact and applied-resolved are disclosed separately |
| `ipcfg::find_disabled <output>` | Scans raw execute output for non-fatal `disabled parameter`/`[BD 41-721]` warnings (gated params that `catch` returns 0 for). Returns `DISABLED:...` or `""` |
| `ipcfg::param_format <cell> <key>` | Reads a key back so you can learn its **shape** (comma list, nested `{{...}}`, etc.) |
| `ipcfg::try_automation <cell> <rule> ?config?` | Generic `apply_bd_automation -rule <rule>` (Designer Assistance) |
| `ipcfg::add_stub <cell> <pin> <intf_vlnv> ?prop? ?val?` | Boundary interface port for connection-derived params; mode auto-mirrors the pin |
| `ipcfg::cleanup <cell> ?orig_part?` | Deletes `STUB_*` ports, the cell, and restores the part if given |
| `ipcfg::cache_get <ip> <feature>` | **Consult first** (0 MCP calls): returns the earned discovery entry (param/shape/enabler/value_src/doc/version) as JSON, or `""` on miss |
| `ipcfg::cache_put <ip> <feature> <param> <shape> <enabler> <value_src> <doc> <ipver>` | **Write back** a confirmed mapping. Stores discovery facts only — **never** the prompt's expected value (blind-safe) |
| `ipcfg::cache_dump` | Print the whole learned cache (debug) |

**Concise per-prompt template** (replaces the verbose phase-by-phase script — the phases
below are still the mental model, but the helpers collapse each to one line):

```tcl
set cell <cell_name>
set orig [get_property PART [current_project]]
# Phase 0+1: MANDATORY availability gate over the candidate shortlist (Step 0a'), then swap
# ONLY on WRONG_PART. Never substitute a different IP because it happens to be AVAILABLE.
set av [ipcfg::ip_availability {<function-glob e.g. *clk*wiz*>}]
puts $av
if {[string match "*<name>=ABSENT:*" $av]} { puts "CONFIGURE_FAIL:VLNV_NOT_FOUND"; return }
if {[string match "*<name>=WRONG_PART:*" $av]} {
    # confirm the target BEFORE the destructive swap, then swap (guarded -- see Step 0)
    puts [ipcfg::ip_availability {<name>} <required_part>]
    puts [ipcfg::ensure_part <required_part>]   ;# may return WARN:SWAP_BLOCKED -> confirm in interactive mode
}
# Phase 2+3 in ONE call: create + parameterize (snapshot defaults first for the intent audit)
set d [list CONFIG.PARAM_A {a} CONFIG.PARAM_B {b}]
puts "APPLY:[ipcfg::create_cell_cfg <vendor:library:name> $cell $d]"
set base [ipcfg::snapshot $cell [dict keys $d]]   ;# (defaults still readable for unset keys)
set bad [ipcfg::verify_stuck $cell $d]
# Build reqmap {key want baseline ...} for the "enable/select" requirements:
set req {}
foreach {k v} $d { lappend req $k $v [dict get $base $k] }
set suspect [ipcfg::verify_intent $cell $req]
# A value can stick, match intent, and still do nothing because its feature is off:
set inert [ipcfg::check_enablers $cell $d]
# For every signal/feature the prompt asks to have or expose, check its flag directly:
puts [ipcfg::feature_flags $cell {<nouns from the prompt: reset locked interrupt ...>}]
if {[llength $bad] == 0 && [llength $suspect] == 0 && $inert eq ""} {
    puts "SUCCESS: $cell configured"
} elseif {[llength $bad] != 0} {
    puts "STUCK_FAIL:$bad"
} elseif {$inert ne ""} {
    puts "INERT_FAIL:$inert"   ;# set the named enabler and re-apply
} else {
    puts "INTENT_FAIL:$suspect"
}
# Finally, emit coverage from the requirement ledger (REQUIRED when not fully applied):
# ledger = {"<prompt phrase>" CONFIG.PARAM_A applied  "<prompt phrase>" CONFIG.PARAM_B unapplied:integration-derived ...}
puts [ipcfg::coverage_report $ledger]
```

Note: `create_cell_cfg` is the single-call fast path. When you need ordered/multi-pass
configuration (enablers first — see Phase 3), create with the enabler dict, then use
`ipcfg::apply_dict` for the dependent pass.

`verify_stuck` is strictly stronger than the old existence-only loop: it catches the IPI
**silent revert** case where a key exists but the value snapped back (e.g. a peripheral
`ENABLE` that reverts to `0`), which a `get_property` existence check misses. You still scan
the raw output for warning patterns as a backstop, but `STUCK_FAIL:` is the primary signal.

**Intent audit (the non-error failure mode) — required.** `verify_stuck` only proves the
params *you chose* persisted; it cannot tell whether you chose the *right* param for a named
feature. The most dangerous benchmark failure is a **wrong-but-valid** param: it exists, it
accepts your value, it sticks — no error, no `STUCK_FAIL`, no warning — so error-driven
Tier 2 never fires and the prompt silently scores as a false success. To catch this without
any IP-specific knowledge, `snapshot` the baseline *before* configuring, then run
`verify_intent` *after*:

- A requirement that means **enable/select/turn-on** must produce an **observable change
  from the default**. If the param you set was *already* at the requested value by default
  (`suspect-no-change`), you almost certainly set the wrong param — the param that truly
  implements the feature is still sitting at its default.
- A non-empty `verify_intent` list is a **new Tier-2 trigger** (`INTENT_FAIL`) even though
  nothing errored: go back to Step 2, re-read the doc descriptions for the suspect
  requirement, remap to the correctly-grounded param, and re-apply.
- Cross-check against the Step 1.5 ledger: every requirement must be observably realized,
  not merely "set without error."

The remainder of Step 3 documents the phases the helpers implement, plus the
error/format/automation/stub recovery patterns. Use the helpers; drop to raw TCL only for an
IP-specific quirk a helper does not cover.

### Step 3: Build and execute the -dict

Compose a SINGLE TCL script with four phases: part swap (if needed), VLNV validation,
cell creation, and configuration. Use `catch` around every mutating command so errors
produce parseable output instead of aborting the script.

```tcl
# /tmp/configure_<ip_name>.tcl

# --- Phase 0: Part swap (only if IP needs a different device family) ---
# AI: set _need_swap to 1 and _target_part to the required part when
# the doc search or fallback map indicates a part change is needed.
# Omit this entire block when no swap is needed.
set _orig_part [get_property PART [current_project]]
set _target_part "<required_part>"
set _need_swap [expr {$_orig_part ne $_target_part}]
if {$_need_swap} {
    close_bd_design [current_bd_design]
    set_property PART $_target_part [current_project]
    open_bd_design [get_files benchmark_bd.bd]
    puts "PART_SWAP:$_orig_part->$_target_part"
}

# --- Phase 1: VLNV pre-validation ---
set _vlnv_matches [get_ipdefs -filter {VLNV =~ "<vendor:library:name>:*"}]
if {$_vlnv_matches eq ""} {
    if {$_need_swap} {
        close_bd_design [current_bd_design]
        set_property PART $_orig_part [current_project]
        open_bd_design [get_files benchmark_bd.bd]
    }
    puts "CONFIGURE_FAIL:VLNV_NOT_FOUND:<vendor:library:name> not available for $_target_part"
    return
}

# --- Phase 2: Create cell ---
if {[llength [get_bd_cells <cell_name>]] == 0} {
    if {[catch {create_bd_cell -type ip -vlnv <vendor:library:name> <cell_name>} _err]} {
        if {$_need_swap} {
            close_bd_design [current_bd_design]
            set_property PART $_orig_part [current_project]
            open_bd_design [get_files benchmark_bd.bd]
        }
        puts "CONFIGURE_FAIL:CREATE_ERROR:$_err"
        return
    }
}

# --- Phase 3: Apply configuration with structured error handling ---
set _prop_dict [list \
    CONFIG.PARAM_A {value_a} \
    CONFIG.PARAM_B {value_b} \
    CONFIG.PARAM_C {value_c} \
]
# Empty-dict guard: set_property -dict {} throws "Missing name/value pair".
# For "default settings" prompts where intent == defaults, skip configuration.
if {[llength $_prop_dict] == 0} {
    puts "SUCCESS: <cell_name> created with default configuration"
    return
}
if {[catch {set_property -dict $_prop_dict [get_bd_cells <cell_name>]} _cfg_err]} {
    set _err_type "UNKNOWN"
    if {[string match {*does not exist*} $_cfg_err]}      {set _err_type "PARAM_NOT_FOUND"}
    if {[string match {*is out of the range*} $_cfg_err]}  {set _err_type "VALUE_OUT_OF_RANGE"}
    if {[string match {*read-only*} $_cfg_err]}            {set _err_type "READ_ONLY"}
    if {[string match {*It is read-only*} $_cfg_err]}      {set _err_type "READ_ONLY"}
    if {[string match {*not supported*} $_cfg_err]}        {set _err_type "NOT_SUPPORTED"}
    puts "CONFIGURE_FAIL:${_err_type}:$_cfg_err"
    return
}

# --- Phase 3 verification: catch SILENTLY-IGNORED params (IPI CRITICAL WARNINGs) ---
# In BD mode an unknown CONFIG key emits a non-fatal CRITICAL WARNING and catch returns 0,
# so the dict above can "succeed" without applying. Verify every key actually exists on the
# cell. get_property on a specific, already-set key is verification (not parameter discovery),
# so it does not violate the "no list_property/report_property" rule.
set _missing {}
foreach {_k _v} $_prop_dict {
    if {[catch {get_property $_k [get_bd_cells <cell_name>]}]} {
        lappend _missing $_k
    }
}
if {[llength $_missing] > 0} {
    puts "CONFIGURE_FAIL:PARAM_NOT_FOUND:silently ignored (do not exist): $_missing"
    return
}

puts "SUCCESS: <cell_name> configured"
```

**Output-scan backstop:** Even with the verification loop above, after `vivado_execute`
returns, scan its full stdout for `Cannot set the parameter`, `does not exist`,
`Invalid parameter`, or `Ignoring`. If any appear, treat the result as
`CONFIGURE_FAIL:PARAM_NOT_FOUND` regardless of whether a `SUCCESS:` line was printed — the
warning may reference a parameter the loop could not catch (e.g. a key inside a nested dict).

**Nested-dict params:** When a CONFIG value is itself a dictionary (e.g.
`CONFIG.CPM_CONFIG {...}`, `CONFIG.PS_PMC_CONFIG {...}`, or a transceiver-wizard config),
invalid *sub-keys* are silently dropped with `[IP_Flow 19-7090] ... Ignoring`. The
top-level `get_property` check above will pass even though sub-keys were ignored.
`ipcfg::verify_stuck` already inspects `*_CONFIG` keys sub-key by sub-key, so a non-empty
`STUCK_FAIL` list names the exact sub-keys that did not apply.

**STUCK recovery — value-format introspection (generic, no per-IP table):** The most common
reason a key reverts (rather than erroring) is that your **value shape** does not match what
the IP expects. This is fully recoverable without any IP-specific knowledge:

1. Read the current value back with `ipcfg::param_format <cell> <key>` to learn the shape.
2. **Mirror that shape**, substituting your target value:
   - **Comma-list params** (e.g. Versal `clk_wizard`): `CLKOUT_USED` reads back as
     `true,false,false,...` and `CLKOUT_REQUESTED_OUT_FREQUENCY` as a comma list — supply one
     comma-separated string per the read-back length, **not** per-clock keys.
   - **Nested list-of-pairs sub-keys** (e.g. Versal `versal_cips` peripherals): a peripheral
     sub-key reads back as `{{ENABLE 0} {IO {PS_MIO 0 .. 1}}}`. To enable it, re-send the
     **same structure** with `ENABLE 1` (keep the read-back `IO {...}` routing). Sending a
     flat `{ENABLE 1}` is silently rejected.
   - **Scalar mismatch**: just supply the documented value/units the read-back implies.
3. Re-apply and re-run `verify_stuck`. Only after a format-mirrored retry still fails do you
   grade `creation_only`/`partial`.

This single read-back-then-mirror loop replaces any per-IP value-format table — it works for
any param whose value snapped back, because the IP itself tells you the shape it wants.

**RESOLVED ≠ reverted (do not retry a value the IP legally snapped):** Some params are
*requests* the IP quantizes to the nearest achievable value (PLL/MMCM frequencies, divider
ratios, lane counts rounded to a legal set). A read-back of 597.20 for a requested 600 MHz is
**not** a failure — it is the IP resolving the request. `verify_intent`/`audit_intent` already
treat this as `RESOLVED` (via `classify_change`) and pass it, so you neither retry it nor
grade it `creation_only`. Record it in the coverage ledger as `applied-resolved:<achieved>`
so the request-vs-achieved difference is disclosed. Use a full-config baseline + diff to see
both the resolution and any IP side effects in one shot:
```tcl
set base [ipcfg::snapshot_all $cell]
ipcfg::apply_dict $cell $d
puts [ipcfg::config_diff $cell $base $d]   ;# {key old new EXACT|RESOLVED|REVERTED|CHANGED ...}
```

**Automation-first for SYSTEM intent (do this BEFORE fighting gated CONFIG):**
Run `ipcfg::is_system_intent <prompt>` first. If it returns `SYSTEM:{...}` (integrated
memory controllers, a PCIe controller, PS PL-clocks/peripherals), the prompt describes a
*subsystem* that Vivado realizes through **block automation** / a **Configurable Example
Design**, not through plain standalone `CONFIG.*`. Fighting the gated CONFIG there wastes
calls (validated: `NUM_MC`/`NUM_MCP` on a bare `axi_noc2` cell are **disabled** and every
`set_property` is silently ignored with `[IP_Flow 19-3374] ... disabled parameter ...
ignored`). Do **not** hardcode which IPs need it. Instead:

1. **Enumerate the loaded rules directly from Vivado** (the authoritative source — `get_bd_automation_rules` does *not* exist, but the internal rule manager does dump the registry). Run, in one execute, the rule dump and read the printed `[DBG] RulesMap:` block:
   ```tcl
   ::bd::util_cmd rules dump
   # prints: "<vlnv>":["<description>", "<rule-short-name>", "<rules.tcl path>"]
   ```
   The dump is a C-level message (it does **not** return a value and cannot be captured
   in-proc), so read it from the execute **output**. Find the row whose key matches your
   cell's VLNV; the **2nd quoted field is the rule short-name**, and the rule id is
   `xilinx.com:bd_rule:<short>` (validated: `axi_noc2`, `ps_wizard`, `versal_cips`,
   `pcie_versal`, `microblaze`, … all have rules). If you have the dump text in a Tcl var,
   `ipcfg::rule_for_vlnv $dump <vlnv>` extracts the id for you. The 3rd field is the rule's
   `rules.tcl`/`bd.tcl` path — open it (or `vivado_doc_search`) to learn the rule's `-config`
   option names. Also check whether the IP ships a **Configurable Example Design**.
2. **Apply + harvest** so you can confirm the result against intent (this is the
   automation-first path; it gets its **own** Tier-2 budget, separate from the per-param
   retry cap). Pass the rule's options — a **bare apply is often a no-op** for subsystem
   features (validated: `apply_bd_automation -rule xilinx.com:bd_rule:axi_noc2` with no
   `-config` leaves `NUM_MC` at 0; the MC options must be supplied):
   ```tcl
   set base [ipcfg::snapshot_all $cell]
   puts [ipcfg::apply_automation_harvest $cell xilinx.com:bd_rule:<short> {<opt> <val> ...} $base]
   # -> HARVEST:changed={key old new EXACT|RESOLVED|CHANGED ...} new_cells={...}
   ```
   Read the harvest: the `changed` keys (and any `new_cells`) are what automation set — match
   them to the requirement instead of guessing gated CONFIG. (`ipcfg::try_automation` still
   exists for a fire-only apply when you do not need the harvest.)
3. **(interactive)** When multiple rules / example designs could apply, ask the user
   (clickable) which to apply rather than guessing.

Per the give-up gate, you may not grade a requirement `integration-derived` until **either**
the rule dump shows no rule for the VLNV (and no example design realizes it) **or** the rule
was applied with its options and its harvest did not produce the value. A `SYSTEM` intent
whose params are disabled with **no** rule/enabler is legitimately integration-derived —
report it via the coverage report, do not fake a value.

For `versal_cips`, note (validated) that PL-clock frequencies, `PS_NUM_FABRIC_RESETS`, and
`PS_USE_PMCPL_CLK*` **do** stick directly inside `CONFIG.PS_PMC_CONFIG`; automation is for
generating the external clk/reset **wiring**, not for setting those values. Always prefer the
direct nested-dict path when `verify_stuck` confirms it stuck, and fall back to automation
(per docs) only for connectivity the dict cannot express.

**Phase 3 procedure — enabler-first, multi-pass (the default, not an exception):**
Treat ordered configuration as the *normal* path, not a special case. Many params are
**gated**: they only become settable once a parent param selects a mode/type/topology or
turns a feature on. Setting a gated child before its enabler makes the child silently
**disabled/ignored** (see `PARAM_DISABLED` recovery in Step 5). So, by default:

1. **Pass 1 — enablers first:** set the params that *select or enable* something —
   mode/type/device-selection, topology, channel/controller counts, and feature
   `ENABLE` toggles. These are the params other params depend on.
2. **Pass 2 — dependents:** set the params that only make sense once Pass 1 applied.
3. **Verify:** run `verify_stuck` + `verify_intent` + **`check_enablers`** after Pass 2.

How to tell which params are enablers — **ask the cell, do not infer**. `ipcfg::feature_flags
<cell> {<nouns from the prompt>}` lists the boolean params on this cell that enable those
nouns, with their current values, so Pass 1 is built from the live parameter list rather
than from a guess about naming. Docs and compound phrasing ("select device type X, then
configure its N controllers") remain useful corroboration, and `find_disabled` /
`PARAM_DISABLED` feedback still corrects the ordering when a gate is not name-shaped.

**The gated write that reports success — read this before declaring `full`.** An attribute
whose feature is switched off is *not* rejected: it applies, it reads back, `verify_stuck` is
empty, and the IP silently has no such port. Measured on `clkx5_wiz`: with `CONFIG.RESET_TYPE
ACTIVE_LOW` set and `USE_RESET` left `false`, `RESET_TYPE` reads `ACTIVE_LOW` while the cell's
pins are exactly `{clk_in1 clk_out1}` — the requested active-low reset does not exist. Setting
`USE_RESET true` is what grows `resetn`. So **a request for a signal or feature needs its flag,
not just its attribute**: run `ipcfg::check_enablers <cell> <dict>` after every apply and treat
a non-empty `INERT:` line as an unfinished configuration, not a warning.

Concrete IP examples that need this ordering (illustrative, not exhaustive — RFDC mixer
type requires tile/slice enables; `v_tc` generator sizes require `max_lines_per_frame`).
Split Phase 3 into ordered passes within the same script:

```tcl
# --- Phase 3a: Enable parent features first ---
set_property -dict [list \
    CONFIG.ENABLE_PARENT {1} \
    CONFIG.PARENT_MODE  {some_mode} \
] [get_bd_cells <cell_name>]

# --- Phase 3b: Set dependent params (now valid) ---
set _prop_dict [list \
    CONFIG.CHILD_PARAM_A {value_a} \
    CONFIG.CHILD_PARAM_B {value_b} \
]
if {[catch {set_property -dict $_prop_dict [get_bd_cells <cell_name>]} _cfg_err]} {
    # ... error handling as above ...
}
```

IPs known to require multi-pass ordering:

| IP | Pass 1 (enables) | Pass 2 (dependent) |
|---|---|---|
| `rfdc` | Tile enable, slice enable, sampling rate | Mixer type, NCO freq, decimation |

Note: `v_tc` GEN_* timing parameters (VACTIVE, HACTIVE, frame sizes) are
runtime AXI-Lite register values programmed by the VTC driver, not design-time
CONFIG properties. Only `enable_generation` and `max_lines_per_frame` are
design-time params.

**Phase 4 — Stub connections for connection-derived params (generic):** Some parameters are
read-only in BD because their value propagates from an interface connection, not
`set_property`. After Phases 1-3 succeed, attach a boundary interface port with
`ipcfg::add_stub` — it auto-detects the pin's interface VLNV requirement (you pass the VLNV)
and **mirrors the pin's mode** (an external port attached to a `Slave` pin must itself be a
`Slave` port; passing the wrong mode yields `[BD 41-172] modes ... do not match`):

```tcl
puts [ipcfg::add_stub $cell <pin_name> <intf_vlnv> ?<CONFIG_prop> <val>?]
# e.g. drive an AXI-Stream slave input so the cell adopts the connected width:
puts [ipcfg::add_stub $cell S_AXIS xilinx.com:interface:axis_rtl:1.0 TDATA_NUM_BYTES 8]
```

**Important nuance (validated):** for many AXI-Stream *receive* inputs the width parameter is
**read-only on the boundary port too** (`[BD 41-737] ... TDATA_NUM_BYTES ... read-only`) —
the width is inherited from whatever master is connected at integration time, and a bare
boundary port has no master to define it. `add_stub` tolerates this (the property set is
wrapped in `catch`): the connection still elaborates, but you **cannot force** the width
standalone. When the target width param is still wrong after the stub, that feature is
genuinely **integration-derived** — grade `partial` and record the param in `runtime_params`,
do not keep fighting it. Use stubs to *enable elaboration / drive settable port widths*, not
to fake values the datapath must supply.

`ipcfg::cleanup <cell> ?orig_part?` removes all `STUB_*` ports (and their nets), deletes the
cell, and restores the part if you pass the original — so a single call replaces the manual
stub/port/part teardown.

**When no part swap is needed**, omit Phase 0 entirely and remove the `_need_swap`
restore blocks — the script simplifies to Phases 1-3 (and optionally Phase 4) only.

**Cleanup TCL (always runs after recording results):**

```tcl
# One call deletes STUB_* ports + the cell, and restores the part if it was swapped.
# Pass $orig only when a swap happened; omit (or pass "") otherwise.
puts [ipcfg::cleanup <cell_name> $orig]
```

This replaces the manual `delete_bd_objs` / part-restore blocks. It is safe to call even when
no stubs or swap were used (the port/part steps are no-ops).

Execute:
```
vivado_execute("source /tmp/configure_<cell_name>.tcl")
```

### Step 4: Handle result

Parse the output line. Possible prefixes:

| Output Prefix | Meaning | Next Step |
|---|---|---|
| `SUCCESS:` | All parameters applied | Run the self-audit below before reporting |
| `STUCK_FAIL:...` | A key reverted / was silently ignored | Tier 2: format-mirror retry or `PARAM_DISABLED` recovery |
| `INTENT_FAIL:...` | A key is `suspect-no-change` (likely wrong param) | Tier 2: remap via doc descriptions, re-apply |
| `CONFIGURE_FAIL:VLNV_NOT_FOUND:...` | IP not available even after part swap | Record failure — no retry |
| `CONFIGURE_FAIL:<err_type>:...` | Configuration error | Enter Tier 2 using `<err_type>` |

Note: `PART_SWAP:` lines are informational — record the target part in results as
`part_swapped`.

**Self-audit before declaring SUCCESS (required):** A `SUCCESS:` line is *necessary but
not sufficient*. Before reporting, confirm all of:
1. `ipcfg::verify_stuck` returned empty (no revert).
2. `ipcfg::verify_intent` flagged no **hard reverts**. A `suspect-no-change` (value already
   equalled the default) is a **soft** flag, not an automatic failure: re-read the doc
   description for that requirement. If the param you set is the doc-correct one and its
   default legitimately satisfies the intent, **accept it** and record `value_src=default`
   in the ledger (a user/answer not changing a param does not make the default wrong). Only
   treat it as `INTENT_FAIL` when a *competing* param better matches the doc description —
   then remap and re-apply. (Re-run `verify_intent` with `flag_no_change=0` once you have
   confirmed the grounding, so only hard reverts remain.)
3. `ipcfg::find_disabled <raw_output>` returned `""` (no non-fatal gated-param warning).
4. `ipcfg::check_enablers` returned `""` — **nothing applied is inert**. A non-empty
   `INERT:` line names the flag to set: set it, re-apply, re-check. This is a hard gate, not
   a soft one; the value reading back correctly is exactly why it needs its own check. And
   for every signal/feature the prompt asks to *have* or *expose* (a reset, a locked output,
   an interrupt, a second channel), confirm its flag is on via `ipcfg::feature_flags` — an
   attribute like `RESET_TYPE` alone does not create the port.
5. **Ledger coverage:** every requirement from Step 1.5 is mapped to a param that is
   confirmed by 1–4. Any uncovered or suspect requirement downgrades the result and
   triggers the matching Tier-2 recovery instead of reporting `full`.

### Step 5: Error recovery (Tier 2)

The `CONFIGURE_FAIL` line contains a classified error type. Each type has a
different recovery strategy:

| Error Type | Vivado Message Pattern | Recovery |
|---|---|---|
| `VLNV_NOT_FOUND` | IP unavailable after part swap | Try doc search for correct part, swap again if plausible; otherwise record failure |
| `PARAM_NOT_FOUND` | `[BD 41-1276] Cannot set the parameter X ... does not exist` (hard error) **or** the non-fatal `[BD 41-1276] ... does not exist` / `[IP_Flow 19-7090] Invalid parameter ... Ignoring` caught by the Phase 3 verification loop / output scan | Drop unknown params; doc-search for correct names; rebuild dict |
| `VALUE_OUT_OF_RANGE` | `[IP_Flow 19-3461] Value 'V' is out of the range ... Valid values are - A, B, C` | Parse valid values from the error text; pick closest match; rebuild dict |
| `READ_ONLY` | `[BD 41-737] Cannot set the parameter X ... It is read-only` | Strip read-only params and re-run — **no doc search needed** (saves 1 MCP call) |
| `NOT_SUPPORTED` | `[BD 5-683] VLNV ... is not supported for the current part` | **Should never reach Tier 2** — Step 0a′'s `ipcfg::ip_availability` predicts it before the create, which matters because `catch` here yields only `[Common 17-39] ... failed due to earlier errors` (the 5-683 goes to the log, so there is nothing to classify). If it does fire: re-run the gate, then swap the part — do **not** substitute a different IP |
| `PARAM_DISABLED` | `disabled parameter ... ignored` / `[BD 41-721]` (often **non-fatal** — caught by `ipcfg::find_disabled` or the output scan, not a thrown error) | **Not terminal, not `creation_only`.** Find + set the gating parent first, then re-apply (see below) |
| `INTENT_FAIL` | *No Vivado message* — `verify_intent` flagged a **hard revert**, or a `suspect-no-change` that doc re-check shows a *competing* param better matches | Re-read doc descriptions; remap the suspect requirement to the correctly-grounded param and re-apply. If the param is doc-correct and the default satisfies intent, accept as `value_src=default` (not a failure) |
| `UNKNOWN` | Anything else | Call `vivado_log_messages` for detail, then doc-search |

**For `VLNV_NOT_FOUND` after no part swap was attempted:** The IP may need a
different device family. Use `vivado_doc_search("<ip_name> supported devices")` to
find the correct family, select a part from the fallback map, and retry with a part
swap. This is the one case where Tier 2 can recover from a VLNV failure.

**For `READ_ONLY` errors:** The read-only parameter often already has the desired
default value (e.g., `C_EXT_RESET_HIGH` defaults to active-low). Drop it from the
dict and retry immediately — no doc search, no wasted MCP call:

```tcl
# Tier 2 retry — read-only params stripped
set_property -dict [list \
    CONFIG.PARAM_A {value_a} \
    CONFIG.PARAM_C {value_c} \
] [get_bd_cells <cell_name>]
puts "SUCCESS: <cell_name> configured (read-only params skipped)"
```

**For `VALUE_OUT_OF_RANGE` errors:** Vivado's error text includes the valid set, so this
is the **default zero-doc-search recovery** — never spend an MCP doc call here. Parse the
list directly:
```
Valid values are - 6, 8, 10, 12
```
Then decide deterministically:
- If the requested value maps to a member of the set (or a clear nearest member that still
  satisfies intent), apply it and grade `full`.
- If the requested value is **provably outside** the valid set with no equivalent (e.g. a
  4-tap scaler when the minimum is 6), apply the closest valid value and grade `negative`,
  recording the valid set in `fidelity_note`.

**For `PARAM_DISABLED` errors (gated parameter) — reconcile first, then find the enabler:**
A disabled/ignored parameter means the param is real but currently *gated*. This is
**recoverable** and must never be graded `creation_only` on first sight. Recovery
(IP-agnostic):

1. **Detect it even when non-fatal.** A gated param frequently does not throw — Vivado
   emits a non-fatal warning and `catch` returns 0. Always run
   `ipcfg::find_disabled <raw_output>` (and the output scan) after apply; a `DISABLED:...`
   result is the trigger, not just a thrown `CONFIGURE_FAIL:PARAM_DISABLED`.
2. **Reconcile before hunting an enabler.** Run `ipcfg::reconcile_disabled <cell> <dict>`:
   - **`OMIT:{...}`** — these gated keys already hold the value you wanted (the read-only /
     gated value equals your intent). **Drop them and move on** — no enabler search, no
     re-apply. This saves MCP calls and is the common case.
   - **`DIFFER:{...}`** — only these are genuine problems (gated value ≠ intent). Continue
     to step 3 for the `DIFFER` set only.
3. **Find the enabler via doc search (DIFFER keys only):**
   ```
   vivado_doc_search("<IP name> <gated_param_or_feature> prerequisite enable depends on")
   ```
   Look for the parent param that selects the mode/type/device/topology which un-gates it.
4. **Set the enabler first, then the still-differing gated params** — the enabler-first
   multi-pass from Phase 3:
   ```tcl
   # Pass 1: the enabler the doc named (mode/type/device-selection/feature toggle)
   puts "ENABLER:[ipcfg::apply_dict $cell [list CONFIG.<ENABLER> {<value>}]]"
   # Pass 2: re-apply the DIFFER params (now valid)
   puts "GATED:[ipcfg::apply_dict $cell [list CONFIG.<GATED_A> {a}]]"
   puts "STUCK:[ipcfg::verify_stuck $cell [list CONFIG.<GATED_A> {a}]]"
   ```
5. **Re-verify** with `verify_stuck` + `verify_intent`. Only if a `DIFFER` param still will
   not take *after* the enabler is confirmed set do you grade `partial` (see the tightened
   give-up gate in Step 4), and record that exact prompt fragment as `unapplied:gated-no-enabler`.

This generalizes the validated "live inputs only appear once an IO-type selector is set"
case and any "device-type selection un-gates the controller/channel params" pattern — the
agent discovers the specific enabler from docs, the procedure stays IP-independent.

**For `PARAM_NOT_FOUND` errors:** This is the main case requiring a doc search.
The parameter name in the error is the one to search for:
```
vivado_doc_search("<ip_name> <param_from_error> valid parameter names")
```

**For `PARAM_NOT_FOUND` in BD — standalone IP fallback:** Some CONFIG params
exist in standalone mode (`create_ip`) but are hidden in BD mode (`create_bd_cell`).
When a `PARAM_NOT_FOUND` error occurs for a param that doc search confirms is
valid for the IP, try the standalone path as a validation mechanism:

```tcl
# Tier 2 fallback: standalone IP validation
create_ip -vlnv <vlnv> -module_name <name>_standalone -dir /tmp
set_property -dict [list \
    CONFIG.PARAM_A {value_a} \
    CONFIG.PARAM_B {value_b} \
] [get_ips <name>_standalone]
puts "STANDALONE_OK:<id>"
# Cleanup standalone IP
remove_files [get_files /tmp/<name>_standalone/<name>_standalone.xci]
file delete -force /tmp/<name>_standalone
```

Testing showed that originally hypothesized BD-restricted params
(`axi_timer` C_ONE_TIMER_ONLY, `axis_interconnect` ARB_ALGORITHM,
`axis_switch` DECODER_BASE) are actually not configurable in ANY mode
for current IP versions. The standalone fallback remains available for
future cases where a param genuinely exists in standalone but not BD.

The fidelity grade for standalone-validated configs is `full_standalone`.

**For runtime-only features — annotation instead of failure:** Some requested
features are controlled by software register writes, not design-time CONFIG
properties. When doc search returns a register map instead of CONFIG params,
emit a structured annotation:

```
RUNTIME_CONFIG:<id>:<feature>=<value>:<register>[<bits>]@<offset>
```

Examples:
- `RUNTIME_CONFIG:60:CPOL=1,CPHA=1:SPICR[4:3]@0x60`
- `RUNTIME_CONFIG:100:SPEED_P0=100G,FEC=RS-FEC:PORT0_CONFIGURATION_REV1[7:0]@0x0100`

The benchmark result gets a `runtime_params` field:

```json
{
  "runtime_params": {
    "CPOL": {"value": 1, "register": "SPICR", "bit": 3, "offset": "0x60"},
    "CPHA": {"value": 1, "register": "SPICR", "bit": 4, "offset": "0x60"}
  }
}
```

IPs with known runtime-only features:

| IP | Runtime Feature | Register | Notes |
|---|---|---|---|
| `axi_quad_spi` | CPOL, CPHA | SPICR (0x60) | SPI clock polarity/phase |
| `mrmac` | Port speed, FEC, PTP | Per-port config registers | All port config is runtime |
| `axi_ethernet` | DMA enable | External — DMA is a separate IP | Not a register; requires companion IP |
| `v_tc` | GEN_* timing params | Generation registers (0x60-0x84) | 1080p60 timing is set by VTC driver |

When runtime params are identified, the design-time CONFIG params that ARE
available should still be set via `set_property -dict`. The fidelity grade
becomes `full` (with `runtime_params` populated) since the design-time config
is complete and the runtime portion is documented.

**Give-up gate — do NOT grade `creation_only`/`partial` prematurely.** You may never
conclude a parameter is integration-derived, connection-derived, gated, or runtime-only
**from reasoning alone**. Before downgrading a requirement, you MUST have evidence of all:
1. **You actually attempted the literal value with `set_property` and it failed/reverted.**
   A param you merely *assumed* is derived does not count. In particular:
   - **Try the global / top-level key form, not just per-instance keys.** Many counts and
     widths are set by a single global `CONFIG.<X>` even when per-port `CONFIG.<Sn>_<X>`
     keys are read-only (e.g. a NoC data width applied once globally rather than per slave
     port). Attempt the global key before declaring the value connection-derived.
   - Run `verify_stuck` to confirm it genuinely reverted, not that you skipped it.
2. **Enabler search attempted** (if disabled/ignored): you ran the `PARAM_DISABLED`
   reconciliation (below) and, for any `DIFFER` key, doc-searched + set the gating parent
   first — and the child *still* would not take.
3. **Block Automation checked** (for integration/connectivity features): you ran
   `ipcfg::is_system_intent` and, if `SYSTEM`, enumerated the loaded rules with
   `::bd::util_cmd rules dump` (→ `ipcfg::rule_for_vlnv`) and either no rule exists for the
   VLNV (and no example design realizes it) or `ipcfg::apply_automation_harvest` was applied
   **with the rule's options** and its harvest did not realize the value. Integration-derived
   is only valid after automation could not deliver it.
4. **Doc confirms no design-time path.** A doc search shows the feature is genuinely
   runtime-register-only or integration/connection-derived (not just absent from your dict).

If any of 1–4 is missing, keep recovering — the downgrade is not yet justified. Whatever
you finally cannot apply MUST appear in the Step 1.5 ledger as `unapplied:<reason>` and in
the `ipcfg::coverage_report` output (see "Always report coverage").

**Maximum retries: 2.** If it still fails after 2 Tier-2 attempts, report the error
to the user with the diagnostic info and ask for guidance.

## Performance Targets

| Metric | Target |
|--------|--------|
| Tier 1 success rate (easy prompts) | >90% |
| Tier 1 success rate (medium prompts) | >70% |
| Tier 1 success rate (hard prompts) | >40% |
| Tier 2 recovery rate (when Tier 1 fails) | >80% |
| True fidelity rate (full + full_standalone) | >90% |
| Total MCP calls (Tier 1, no part swap) | 2-3 |
| Total MCP calls (Tier 1, with part swap) | 3-4 |
| Total MCP calls (Tier 2 recovery) | 4-6 |
| Total MCP calls (Phase 4 stub connections) | +1 (added to Tier 1 or 2) |
| Total MCP calls (standalone fallback) | +1 (Tier 2 only) |

## Fidelity Grades

| Grade | Meaning |
|-------|---------|
| `full` | CONFIG params match prompt intent; runtime params documented if applicable |
| `full_standalone` | Config validated via `create_ip` (standalone); param unavailable in BD mode |
| `partial` | IP configured but some features not settable via CONFIG or connections |
| `negative` | Prompt asked for values outside Vivado's valid range |
| `creation_only` | IP created but key requested features aren't CONFIG properties |

## What NOT to do

- **Do not query parameters one at a time** — always use `set_property -dict` for batch ops
- **Do not try to read the full parameter space** before configuring — go straight to the
  -dict. **Exception (sanctioned):** a *keyword-scoped* `ipcfg::discover_params <vlnv>
  <keyword>` on a throwaway scratch cell, used to map a requirement to its COMPLETE sibling
  set. That is targeted neighborhood discovery, not a blind full dump, and is the only
  permitted `list_property` use.
- **Do not retry more than 2 times** — escalate to user
- **Do not hardcode IP versions** — use version-free VLNVs
- **Do not issue individual `set_property` calls** for each parameter — one `-dict`, one call
- **Do not use Phase 4 stubs when the param IS settable via CONFIG** — stubs are only for
  genuinely connection-derived read-only params
- **Do not mix standalone and BD validation** in the same script — standalone is a separate path
- **Do not trust a `catch` of `0` (or a `SUCCESS:` line) alone in BD mode** — unknown params
  emit non-fatal CRITICAL WARNINGs; always run the Phase 3 verification loop and scan output
- **Do not configure an IP that the docs show cannot deliver the requested capability** —
  grade `negative` and name the correct IP instead of forcing an ignored setting
- **Do not spend a doc-search call on a `VALUE_OUT_OF_RANGE` error** — the valid set is in
  the error text; parse it directly
- **Do not hand-roll the repetitive TCL** (part swap, create, dict+verify, stub, cleanup) —
  call the `ipcfg::*` helpers from `lib/ipcfg.tcl` (sourced once per session); drop to raw
  TCL only for a quirk no helper covers
- **Do not declare success on an empty `catch` in BD mode** — a non-empty `STUCK_FAIL` list
  from `ipcfg::verify_stuck` means a key reverted; recover before grading `full`
- **Do not set an attribute and call the feature delivered** — `RESET_TYPE` without
  `USE_RESET`, a parity setting without `C_USE_PARITY`, an SG width without `c_include_sg`:
  the write sticks and the port never appears. `ipcfg::check_enablers` must come back empty
- **Do not guess a reverted param's value shape** — read it back with `ipcfg::param_format`
  and mirror the structure (comma list / nested `{{...}}`) instead of a per-IP format table
- **Do not keep fighting a width that is read-only on the boundary port too** — it is
  integration-derived; grade `partial` and record it in `runtime_params`
- **Do not pick a param by name similarity** — ground every requirement in the param's
  documented *description*; same-keyword params often implement different functions
- **Do not trust a stuck value that equals the default** for an enable/select requirement —
  `verify_intent` flags it `suspect-no-change`; it usually means you set the wrong param
- **Do not grade `creation_only` on a disabled/ignored param** before running the
  `PARAM_DISABLED` reconciliation (`ipcfg::reconcile_disabled`; only `DIFFER` keys need an
  enabler — `OMIT` keys already hold the wanted value)
- **Do not declare SUCCESS on the `SUCCESS:` line alone** — also require empty
  `verify_intent` (hard reverts), empty `find_disabled`, and full Step 1.5 ledger coverage
- **Do not declare a param "derived"/"runtime"/"gated" from reasoning** — you must have an
  actual failed `set_property` (including the global/top-level key form), enumerated the
  loaded automation rules (`::bd::util_cmd rules dump` → `ipcfg::rule_for_vlnv`), and a doc
  citation first (see the give-up gate)
- **Do not swap parts silently mid-design** — `ipcfg::ensure_part` is guarded; on
  `WARN:SWAP_BLOCKED` confirm with the user (interactive mode) before forcing
- **Do not treat `suspect-no-change` as an automatic failure** — a doc-correct param whose
  default satisfies intent is `value_src=default`, which is acceptable
- **Do not finish without disclosing coverage** — when the IP is not fully parameterized,
  emit `ipcfg::coverage_report` and tell the user the exact prompt fragment(s) you could not
  apply and why
- **Do not create-then-configure in two calls when one works** — prefer
  `ipcfg::create_cell_cfg` (single `create_bd_cell -set_param`); fall back to two-step only
  when needed for ordered/multi-pass config
