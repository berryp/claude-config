---
name: garden
description: Run the gardener on a project using the harness - find drift (docs that no longer match the code, stale instructions, rules that could be checks, harness parts that never fire) and propose small fixes. Use when the user says /harness:garden, asks for a cleanup pass, or wants it on a schedule.
---

1. Run the `gardener` agent on the project. It's read-only and returns a
   list of findings, each with evidence and a proposed fix.
2. Show the user the findings, grouped: fix now (small, mechanical, no
   judgment needed), needs a decision, harness changes.
3. Only on the user's yes, make the fixes as small, separate changes
   (one concern each, so each is quick to review), on a branch, following
   the project's process for branches and PRs. Harness changes
   (`.claude/harness.json`) are the user's to approve: list each one
   (the rule, what it does, why), then make the approved ones in one edit.

To run it regularly, offer a scheduled task (weekly is usually enough)
that runs the gardener and reports its findings without changing
anything; the user decides what to fix.
