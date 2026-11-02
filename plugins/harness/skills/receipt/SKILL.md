---
name: receipt
description: Run the final verification and write the change receipt at the end of a task in a project using the harness - what changed, what was verified, what wasn't, decisions, risks, approvals needed. Use before opening a PR or when the user says /receipt.
---

The receipt says what the harness can prove, not what you remember doing.

1. Run the final verification:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify.py"`. It runs every check
   covering the change, final tier included (end-to-end, UI), and the
   contract's acceptance. If it fails, the task isn't done: fix it, or
   write the receipt with that failure first.
2. For a non-trivial change, have the `verifier` agent try to reject it,
   then record its verdict:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/report.py" --verdict ACCEPT`
   (or REJECT). Fix blocking findings and verify again.
3. Build the receipt from:
   - `.claude/state/task.json`: objective, acceptance, not_verified,
     decisions.
   - `git diff --stat $(cat .claude/state/base)` and untracked files.
   - The verify run just made (the last `"kind": "verify"` line in
     `.claude/state/gate.log`). Only its checks count as VERIFIED. Its
     `skipped` checks (not runnable on this platform) and the contract's
     `not_verified` go under NOT VERIFIED. Its `preexisting` failures and
     `notes` go under RISKS.
   - The verifier's verdict and findings.

```
OBJECTIVE        ABC-123: one sentence
CHANGED          - what, by area (not a file list)
VERIFIED         - check: result (from the verify run)
NOT VERIFIED     - what wasn't checked and why
DECISIONS        - choice: reason
RISKS            - pre-existing failures, the gate's notes, verifier minors
APPROVAL NEEDED  - from approval_required, plus anything with an external
                   effect still to do (push, merge, tracker updates)
```

Use it as the PR description's summary and for the ticket update. Don't
post it anywhere unless the user asks or the project's process says to.

If the user later finds a problem the verifier accepted, add it to the
verifier's calibration notes (`.claude/harness-verifier.md`, or
`verifier_notes` in `.claude/harness.json`): what was missed, a short
example from this change, and what would have caught it. Ask the user
first; the file changes how every later change is judged.
