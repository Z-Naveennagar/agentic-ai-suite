<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Contributing to AMD Embedded Agentic AI Suite

This guide walks you through contributing to skills using a Pull Request (PR) workflow. All changes go through code review before being merged to ensure quality and catch issues early.

**Why Pull Requests?** They provide code review, prevent accidental breaking changes, and give visibility into what's changing.

---

## Workstream Assignments & Code Owners

| Workstream | Skill | Code Owners (Both) | Focus Area |
|------------|-------|-------------------|------------|
| Team 1 | `baselining` | @gpocklas + @blaine | Post-synthesis design baselining and QoR assessment |
| Team 2 | `noc-debug` | @gpocklas + @aamirs | NoC debugging for Versal devices |
| Team 3 | `rtl-assistant` | @gpocklas + @shikhas | RTL code analysis and linting |
| Team 4 | `versal-timing-closure-methodology` | @gpocklas | Timing closure workflows |
| Team 5 | `vivado-revision-control` | @gpocklas + @sunayana | Revision control strategies |

**Review Process:**
- Each skill has **two code owners** who are automatically notified of PRs
- **One approval required** from a code owner (but you can't approve your own PR)
- If @blaine submits a baselining change → @gpocklas must approve
- If @gpocklas submits a baselining change → @blaine must approve
- This distributes review load and scales better as the team grows!

---

## First Time Setup (Do Once)

### Step 1: Clone the skills repository

```bash
cd ~
git clone https://gitenterprise.xilinx.com/swm/agentic-ai-suite.git agentic-ai-suite
cd agentic-ai-suite
git sparse-checkout init --cone
git sparse-checkout set skills/YOUR-SKILL-NAME
git checkout main
```

**Replace `YOUR-SKILL-NAME`** with your skill: `baselining`, `noc-debug`, `rtl-assistant`, `versal-timing-closure-methodology`, or `vivado-revision-control`

### Step 2: Link to your Vivado project

```bash
cd /path/to/your-vivado-project
mkdir -p .github && ln -s ~/agentic-ai-suite/skills .github
```

This creates the `.github` directory in your project, with `skills` as a symlink to the shared repository.

Repeat Step 2 for each Vivado project you work on. Now your Vivado projects can use the skills!

---

## Development Workflow (Pull Request Based)

Here's the complete workflow from making changes to getting them merged:

```
Your Changes → Create Branch → Push → Create PR → Review → Approval → Merge to Main
```

### Step 1: Get Latest Changes

Always start with the latest code:

```bash
cd ~/agentic-ai-suite
git checkout main
git pull origin main
```

### Step 2: Create a Feature Branch

**Important:** You can't push directly to `main` anymore. Create a branch for your changes:

```bash
git checkout -b skill/YOUR-SKILL-NAME/brief-description
```

**Branch naming examples:**
- `skill/baselining/fix-cdc-report`
- `skill/noc-debug/add-validation-checks`
- `skill/rtl-assistant/update-documentation`

### Step 3: Make Your Changes

**Always work from your Vivado project workspace:**
```bash
cd /path/to/your-vivado-project
code .
```

- Edit skill files at `skills/YOUR-SKILL-NAME/` in your Vivado project
- Changes are automatically reflected in the git repo via the symlink
- Test changes with your actual Vivado project to ensure they work
- Use Copilot chat to verify skills work as expected

**Important:** Do not edit files directly in `~/agentic-ai-suite/`. Always make changes through the symlinked `skills/` directory in your Vivado project workspace so you can test your changes properly.

### Step 4: Commit Your Changes

```bash
cd ~/agentic-ai-suite
git add .
git commit -m "Clear description of what you changed and why"
```

**Good commit message examples:**
- `"Fix CDC clock domain crossing detection in baselining skill"`
- `"Add example for NoC bandwidth calculation"`
- `"Update timing closure methodology for Versal AI Edge"`

**Avoid vague messages like:** `"updates"` or `"fixes"`

### Step 5: Push Your Branch

```bash
git push origin skill/YOUR-SKILL-NAME/brief-description
```

If this is your first push, you might see instructions to set upstream - just copy/paste the suggested command.

### Step 6: Create a Pull Request

After pushing, GitHub Enterprise will show you a link to create a PR. **Or do it manually:**

1. Go to: https://gitenterprise.xilinx.com/swm/agentic-ai-suite
2. You'll see a yellow banner: **"skill/YOUR-SKILL-NAME/... had recent pushes"**
3. Click **"Compare & pull request"
4. Fill out the PR form:
   - **Title:** Brief summary (e.g., "Fix CDC checks in baselining skill")
   - **Description:** 
     - What changed?
     - Why did you make this change?
     - How did you test it?
5. Click **"Create pull request"**

**What happens next?** 
- Both code owners for your skill are automatically notified
- One of them must approve (but you can't approve your own PR)
- Example: For baselining changes, both @gpocklas and @blaine get notified, and either can approve

### Step 7: Wait for Review

- Both code owners for your skill get notified (usually review within 1-2 business days)
- One of them must approve (but you can't approve your own changes)
- The reviewer(s) might:
  - ✅ **Approve** - Your PR is ready to merge!
  - 💬 **Request changes** - They'll leave comments on what needs fixing
  - ❓ **Ask questions** - They want clarification

### Step 8: Address Review Comments (If Needed)

If changes are requested:

```bash
cd ~/agentic-ai-suite
# Make sure you're on the SAME branch you used to create the PR
git checkout skill/YOUR-SKILL-NAME/brief-description

# Edit files based on feedback

# Commit the fixes
git add .
git commit -m "Address review feedback: [what you fixed]"

# Push to the SAME branch - this automatically updates your PR!
git push origin skill/YOUR-SKILL-NAME/brief-description
```

**Important:** Always use the **same branch name** you created initially. When you push new commits to the same branch, your Pull Request automatically updates with the new changes. You don't need to create a new PR!

The PR automatically updates with your new commits. Reply to review comments to let the reviewer know you've addressed them.

### Step 9: Merge Your PR

Once approved:
1. Click **"Merge pull request"** on the GitHub Enterprise page
2. Confirm the merge
3. Delete your branch (GitHub will prompt you - it's safe to do)

**Your changes are now live!** Everyone pulling `main` will get your updates.

### Step 10: Clean Up Locally

```bash
cd ~/agentic-ai-suite
git checkout main
git pull origin main
git branch -d skill/YOUR-SKILL-NAME/brief-description  # Delete your local branch
```

---

## Common Scenarios

### Making Quick Fixes

Same workflow as above - even small changes need PRs. The review will be fast!

### Working on Multiple Changes

Create separate branches for each logical change:
```bash
git checkout main
git checkout -b skill/baselining/fix-timing-checks
# ... work, commit, push, create PR ...

git checkout main
git checkout -b skill/baselining/add-examples  
# ... work, commit, push, create PR ...
```

This keeps changes isolated and makes review easier.

### Keeping Your Branch Updated

If `main` changes while you're working on your branch:

```bash
git checkout main
git pull origin main
git checkout skill/YOUR-SKILL-NAME/brief-description
git merge main
# Resolve any conflicts if needed
git push origin skill/YOUR-SKILL-NAME/brief-description
```

---

## Best Practices

### ✅ Do This
- **Test your changes** with a real Vivado project before creating the PR
- **Keep PRs focused** - One logical change per PR
- **Write clear descriptions** - Help the reviewer understand your changes
- **Respond to feedback** - Address comments promptly and politely
- **Update documentation** - If you change behavior, update SKILL.md
- **Include license headers** - All SKILL.md files need SPDX headers, all source files need copyright headers, and all markdown files need the AMD copyright footer (see [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md#license-compliance-mandatory))

### ❌ Avoid This
- **Don't try to push directly to `main`** - It's blocked and will fail
- **Don't make huge PRs** - Break them into smaller, reviewable chunks
- **Don't leave PRs hanging** - Check back daily for review feedback
- **Don't merge without approval** - Wait for the code owner's approval

---

## Troubleshooting

### "I can't push to main!"

**This is expected!** The `main` branch is protected. Use the PR workflow:
```bash
git checkout -b skill/YOUR-SKILL-NAME/my-change
# ... make changes ...
git push origin skill/YOUR-SKILL-NAME/my-change
# Then create PR via GitHub Enterprise
```

### "Who will review my PR?"

Both code owners for your skill are automatically assigned (see the [Workstream Assignments](#workstream-assignments--code-owners) table).

One of them must approve, but you can't approve your own PR. This distributes the review workload and prevents bottlenecks!

### "My PR says 'Changes requested' - what do I do?"

1. Read the review comments carefully
2. Make the requested changes on your branch
3. Commit and push the updates
4. Reply to the comments explaining what you fixed
5. The reviewer will re-review

### "How do I update my PR after creating it?"

Just push more commits to the same branch:
```bash
git checkout skill/YOUR-SKILL-NAME/brief-description
# ... make more changes ...
git add .
git commit -m "Additional changes"
git push origin skill/YOUR-SKILL-NAME/brief-description
```

The PR automatically updates!

### "I made a mistake in my commit message"

If you haven't pushed yet:
```bash
git commit --amend -m "New better message"
```

If you already pushed, don't worry - just add a new commit with a good message.

### "Can I close my PR without merging?"

Yes! If you decide the changes aren't needed:
1. Go to the PR on GitHub Enterprise
2. Click "Close pull request" (don't merge)
3. Delete your branch

---

## Quick Reference

### Starting New Work
```bash
cd ~/agentic-ai-suite
git checkout main
git pull origin main
git checkout -b skill/YOUR-SKILL-NAME/brief-description
# ... edit files ...
git add .
git commit -m "Clear description"
git push origin skill/YOUR-SKILL-NAME/brief-description
# Create PR via GitHub Enterprise UI
```

### Updating Your PR
```bash
cd ~/agentic-ai-suite
git checkout skill/YOUR-SKILL-NAME/brief-description
# ... edit files ...
git add .
git commit -m "Address review feedback"
git push origin skill/YOUR-SKILL-NAME/brief-description
# PR updates automatically
```

### After Merge
```bash
cd ~/agentic-ai-suite
git checkout main
git pull origin main
git branch -d skill/YOUR-SKILL-NAME/brief-description
```

### Get Latest Updates
```bash
cd ~/agentic-ai-suite
git checkout main
git pull origin main
```

---

## Need Help?

- **Review taking too long?** Ping your code owner directly
- **Not sure about a change?** Create a PR anyway and ask in the description
- **Technical questions?** Contact your workstream lead (see table above)
- **Repository issues?** Contact @gpocklas

**Repository:** https://gitenterprise.xilinx.com/swm/agentic-ai-suite
