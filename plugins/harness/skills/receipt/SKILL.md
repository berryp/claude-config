---
name: receipt
description: Write the change receipt at the end of a task in a project using the harness - what changed, what was verified, what wasn't, decisions, risks, approvals needed. Use before opening a PR or when the user says /receipt.
---

The receipt says what the harness can prove, not what you remember doing.
Build it from:

- `.claude/state/task.json`: objective, acceptance, decisions.
- `git diff --stat $(cat .claude/state/base)` and untracked files.
- `.claude/state/gate.log`, the last entry for this tree. Only its checks
  count as VERIFIED, its `skipped` checks (not runnable on this platform)
  go under NOT VERIFIED, and its `notes` go under RISKS. NO CHECKS means the
  project's rules passed but no check covered what changed: say what
  should have checked it. If the last entry is UNVERIFIED or BLOCKED, or
  there's none since the last change, say so first: the task isn't
  proven done.
- The verifier's verdict, if it ran.

```
OBJECTIVE        ABC-123: one sentence
CHANGED          - what, by area (not a file list)
VERIFIED         - check: result (from gate.log)
NOT VERIFIED     - what wasn't checked and why (UI, real devices,
                   production services, platforms not available here)
DECISIONS        - choice: reason
RISKS            - including the gate's notes
APPROVAL NEEDED  - from approval_required, plus anything with an external
                   effect still to do (push, merge, tracker updates)
```

Use it as the PR description's summary and for the ticket update. Don't
post it anywhere unless the user asks or the project's process says to.
