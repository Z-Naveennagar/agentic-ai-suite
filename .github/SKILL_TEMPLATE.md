# Vivado Agentic AI Skill Template

**Version:** 1.0  
**Last Updated:** January 16, 2026

---

## Template Structure

Copy this template when creating a new skill. All sections marked **[MANDATORY]** must be included.

---

```markdown
---
name: [skill-name]
description: [Single sentence describing what this skill does and when to use it. This is used by AI for skill routing.]
version: 1.0.0
vivado_version: [2025.1+]
categories: [debug, analysis, implementation, verification, reporting]
device_families: [versal, ultrascale+, 7series, all]
estimated_duration: [X-Y minutes]
complexity: [basic, intermediate, advanced]
author: [Team/Person]
---

# [Skill Title]

## Introduction **[MANDATORY]**

**Purpose:** [What this skill accomplishes in 1-2 sentences]

**Target Users:** [Who should use this and when]

**Problem Solved:** [What pain point or challenge this addresses]

**Expected Outcome:** [What users get after running this skill]

**Prerequisites:**
- [ ] [Design state requirement, e.g., "Synthesis must be complete"]
- [ ] [Required files that must exist]
- [ ] [Vivado version requirements]
- [ ] [Hardware requirements if applicable]

**Verification Command:**
```tcl
# Commands to verify prerequisites are met
[Actual TCL commands users/agents can run]
```

---

## DO's **[MANDATORY]**

### ✅ Use This Skill When:

1. **[Specific scenario 1]**
   - Example: "User asks to baseline the design after synthesis"
   - Trigger phrases: "[phrase]", "[alternative phrase]"

2. **[Specific scenario 2]**
   - Example: "Timing violations detected and need systematic resolution"
   - Trigger phrases: "[phrase]", "[alternative phrase]"

3. **[Specific scenario 3]**
   - Example: "Design readiness assessment required before implementation"
   - Trigger phrases: "[phrase]", "[alternative phrase]"

### ✅ Best Practices:

- **[Practice 1]**: [Why this matters]
- **[Practice 2]**: [Why this matters]
- **[Practice 3]**: [Why this matters]

---

## DON'Ts **[MANDATORY]**

### ❌ Do NOT Use This Skill When:

1. **[Inappropriate scenario 1]**
   - **Why:** [Reason this won't work]
   - **Instead Use:** [alternative-skill-name]

2. **[Inappropriate scenario 2]**
   - **Why:** [Reason this won't work]
   - **Instead Use:** [alternative-skill-name]

3. **[Inappropriate scenario 3]**
   - **Why:** [Reason this won't work]
   - **Instead Use:** [Manual process or alternative]

### ❌ Common Mistakes to Avoid:

- **[Mistake 1]**: [Why this causes problems]
- **[Mistake 2]**: [Why this causes problems]
- **[Mistake 3]**: [Why this causes problems]

### ❌ Limitations:

- **[Limitation 1]**: [What this skill cannot do]
- **[Limitation 2]**: [Constraints or boundaries]

---

## Mandatory Workflow **[MANDATORY]**

### Execution Mode

**Type:** [Autonomous / Interactive / Background]  
**Duration:** [Typical execution time]  
**User Intervention Required:** [Yes/No - if yes, at what points]

### Workflow Steps

Execute steps **sequentially** in this exact order:

#### Step 1: [Action Name]
**Objective:** [What this step accomplishes]

**Agent Instructions:**
```
1. [Precise instruction for AI - use imperative voice]
2. [Be specific about tools and commands]
3. [Include validation criteria]
```

**Vivado Commands:**
```tcl
# [Purpose of these commands]
set result [command_name -options value]

# Validation
if {$result == "expected_value"} {
    puts "✓ Step 1 complete: [success message]"
} else {
    error "✗ Step 1 failed: [error details]"
}
```

**Success Criteria:**
- [ ] [Condition that must be true]
- [ ] [Observable outcome]
- [ ] [File/object created]

**On Failure:**
- **Symptom:** [What agent observes]
- **Action:** [What agent should do]
- **Fallback:** [Alternative path or exit]

---

#### Step 2: [Action Name]
**Objective:** [What this step accomplishes]

**Agent Instructions:**
```
1. [Precise instruction]
2. [Specific action]
3. [Validation step]
```

**Vivado Commands:**
```tcl
# [Purpose]
[commands]
```

**Success Criteria:**
- [ ] [Condition]
- [ ] [Outcome]

**On Failure:**
- **Symptom:** [Observable behavior]
- **Action:** [Recovery steps]

---

#### Step 3: [Continue for all steps...]

---

### Decision Tree

```
START
  ↓
[Verify Prerequisites]
  ├─ PASS → Continue
  └─ FAIL → Report missing prerequisites → EXIT with error
  ↓
[Step 1: Execute Action]
  ├─ SUCCESS → Continue
  └─ FAILURE → [Retry once] → [Still fails?] → Report error → EXIT
  ↓
[Decision Point: Condition X met?]
  ├─ YES → [Path A: Steps 2-4]
  ├─ NO  → [Path B: Steps 2', 3', 4']
  └─ UNKNOWN → Report ambiguity → Request user input
  ↓
[Step N: Generate Output]
  ├─ SUCCESS → Validate output format → Report completion → EXIT
  └─ FAILURE → Report error with diagnostics → EXIT
```

---

## Mandatory Inputs **[MANDATORY]**

### Required Inputs

| Input Parameter | Type | Description | Validation | Example |
|----------------|------|-------------|------------|---------|
| [input_name] | [string/file/object] | [What it represents] | [How to validate] | `example_value` |
| [input_name] | [integer/boolean] | [Purpose] | [Valid range/values] | `42` |

**Validation Commands:**
```tcl
# Verify required inputs exist and are valid
if {![info exists input_name]} {
    error "Required input 'input_name' not provided"
}
# Additional validation logic
```

### Optional Inputs

| Input Parameter | Type | Default Value | Description |
|----------------|------|---------------|-------------|
| [optional_input] | [type] | [default] | [What it controls] |

### Input Discovery

**How Agent Obtains Inputs:**
1. **From User Query:** [Parse user request for parameters]
2. **From Design Context:** [Extract from open project/design]
3. **From Environment:** [Query Vivado for current state]
4. **Prompt User If Missing:** [What to ask]

**Example Extraction:**
```tcl
# Get current design context
set design_name [get_property NAME [current_design]]
set top_module [get_property TOP [current_fileset]]
# Use these as inputs
```

---

## Mandatory Output **[MANDATORY]**

### Primary Output

**Output Type:** [Report/File/TCL Object/Return Value]  
**Location:** `[absolute/path/to/output]`  
**Format:** [Markdown/JSON/TCL/CSV/Plain Text]

**Structure:**
```
[Exact schema or structure of the output]

Example for Markdown Report:
# [Report Title]
## Summary
- **Status:** [PASS/FAIL/WARNING]
- **Key Finding:** [Most important result]

## Details
[Detailed information]

## Recommendations
1. [Action item 1]
2. [Action item 2]
```

**Sample Output:**
```
[Show concrete example of what output looks like when successful]
```

### Output Validation

**Agent Must Verify:**
```tcl
# Check output exists
if {![file exists "path/to/output"]} {
    error "Output file not generated"
}

# Validate output format
# [Additional validation logic]
```

**Success Indicators:**
- [ ] [File exists at expected location]
- [ ] [Content matches expected schema]
- [ ] [Key metrics within expected ranges]
- [ ] [No error markers in output]

### Secondary Outputs

| Output | Location | Purpose | Format |
|--------|----------|---------|--------|
| [file/object] | [path] | [What it contains] | [format] |

### Output Interpretation

**For Users:**
- **[Key field/metric]**: [What it means, what values indicate]
- **[Status indicator]**: [How to interpret]
- **[Recommendations]**: [How to act on them]

**For Downstream Skills:**
- **Consumed By:** [skill-name] - [what it uses from this output]
- **Format Required:** [Any specific requirements for chaining]

---

## Error Handling **[MANDATORY]**

### Common Errors

#### Error 1: [Error Name/Code]
**Symptoms:**
```
[Error message or observable behavior]
```

**Root Cause:** [Why this happens]

**Agent Actions:**
1. [First diagnostic step]
2. [If condition X, try resolution A]
3. [If condition Y, try resolution B]
4. [If all attempts fail, report to user with actionable guidance]

**User Guidance:**
```
[Exact message to present to user with steps to resolve]
```

**Prevention:** [How to avoid this in the future]

---

#### Error 2: [Next Error]
[Repeat structure]

---

### Recovery Strategy

**For Partial Failures:**
```
[How to resume from checkpoint or rollback]
```

**For Complete Failures:**
```
[How to clean up and exit gracefully]
```

---

## Examples **[MANDATORY]**

### Example 1: [Common Use Case]

**Scenario:** [Describe the situation]

**User Request:**
> "[Exact user phrasing]"

**Agent Workflow:**
1. Parse request → Extract [parameters]
2. Verify prerequisites → [status]
3. Execute Step 1 → [result]
4. Execute Step 2 → [result]
5. Generate output → [location]

**Output Excerpt:**
```
[Show relevant portion of actual output]
```

**Interpretation:**
[Explain what the output means and what user should do next]

**Next Steps:**
- If [condition]: Use [skill-name] to [action]
- If [condition]: Manually [action]

---

### Example 2: [Edge Case]

**Scenario:** [Unusual or challenging situation]

**User Request:**
> "[Phrasing]"

**Agent Workflow:**
[Show how skill handles this case, including any decision branches]

**Output:**
[Show result]

---

## Validation and Testing **[MANDATORY]**

### Self-Validation Checklist

Agent must verify before completing:

```tcl
# Self-validation commands
# 1. Prerequisites were met
# 2. All steps completed successfully
# 3. Output exists and is well-formed
# 4. No warnings or errors in logs
```

- [ ] [Validation point 1]
- [ ] [Validation point 2]
- [ ] [Validation point 3]

### Test Cases

| Test ID | Scenario | Expected Outcome | Status |
|---------|----------|------------------|--------|
| TC-01 | [Normal case] | [Expected result] | ✅ Pass |
| TC-02 | [Edge case] | [Expected result] | ✅ Pass |
| TC-03 | [Error case] | [Expected error handling] | ✅ Pass |

### Quality Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Execution Time | < X minutes | [How to measure] |
| Success Rate | > 95% | [How to measure] |
| Output Accuracy | 100% | [How to validate] |

---

## Integration

### Related Skills

**Upstream (Run Before):**
- **[skill-name]**: Provides [required input/state]

**Downstream (Run After):**
- **[skill-name]**: Consumes [output from this skill]

**Alternative Skills:**
- **[skill-name]**: Use when [different condition]

### Composition Pattern

```
[Skill A] → [This Skill] → [Skill B]
              ↓
        [Alternative: Skill C]
```

---

## References

### Vivado Documentation
- **UG###**: [Document name] - [Relevant sections]
- **AR####**: [Answer record] - [Topic]

### Internal Resources
- [Link to methodology guides]
- [Link to example designs]

---

## Metadata

**Trigger Phrases:**
- "[user phrase 1]"
- "[user phrase 2]"
- "[user phrase 3]"

**Keywords:** [keyword1, keyword2, keyword3]

**Confidence Threshold:** [0.0-1.0 - when to auto-select vs. ask user]

**Maintenance:**
- **Owner:** [Team/Person]
- **Last Reviewed:** [Date]
- **Next Review:** [Date]

---

## Changelog

### Version 1.0.0 (YYYY-MM-DD)
- Initial release
- [Key features]

---

**Quick Reference:**  
`[One-line command to invoke this skill]`
```

---

## License Compliance **[MANDATORY]**

All skill files must include proper license and copyright notices.

### SKILL.md

Add this HTML comment block immediately after the YAML frontmatter closing `---`:

```html
<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
```

### skill-card.md

Every skill directory must contain a `skill-card.md` with a `License: MIT` field:

```markdown
# [Skill Name]

**Description:** [One-line description]

**Owner:** AMD AECG

**License:** MIT
```

### Source Code Files (.py, .sh, .tcl)

Add this header at the top of each file (after the shebang line if present):

```
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
```

### Markdown Files (README.md, references, etc.)

Add the AMD copyright and SPDX license header at the top of every markdown file:

```html
<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
```

---

## Template Guidelines

### For Skill Authors:

1. **Replace all `[placeholder]` text** with actual content
2. **Keep MANDATORY sections** - they are required for all skills
3. **Remove optional sections** if not applicable to your skill
4. **Use concrete examples** - avoid vague descriptions
5. **Write for AI agents** - use imperative instructions, not suggestions
6. **Test your skill** against this template before submitting

### For Reviewers:

Check that PRs include:
- [ ] All MANDATORY sections present
- [ ] DO's and DON'Ts are specific and actionable
- [ ] Workflow steps are sequential and testable
- [ ] Inputs are clearly defined with validation
- [ ] Output structure is documented with examples
- [ ] Error handling covers common failure modes
- [ ] At least 2 examples provided
- [ ] License headers present in SKILL.md and all source files
- [ ] skill-card.md exists with License field
- [ ] Copyright footer on all markdown files

### Version Control:

When updating skills:
- Increment version number
- Update changelog
- Update "Last Reviewed" date
- Document any breaking changes

---

## Questions?

Contact repository maintainers or refer to [SKILL_CONTRIBUTION_WORKFLOW.md](../SKILL_CONTRIBUTION_WORKFLOW.md)
