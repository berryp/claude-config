---
name: contract
description: Write the task contract (.claude/state/task.json) before a non-trivial change in a project using the harness - a ticket, a feature, a fix touching more than one file - or when the user says /contract or the task's scope changes.
---

The contract turns the request into what "done" means, so the gate can
check it and the verifier can judge against it. It is agreed before the
work, not written after it.

1. Read the ticket or request in full. If the project's instructions say
   where work is tracked (an issue tracker, a tracker doc), read the item
   there; if that tool isn't connected, say so.
2. Read only enough of the repo to name the scope.
3. Read `.claude/harness.json` to see which checks already run for the
   paths in scope, and which are final-tier.
4. Write `.claude/state/task.json`:

```json
{
  "issue": "ABC-123",
  "objective": "One sentence: what must be true when this is done.",
  "scope": ["src/parser/", "docs/format.md"],
  "constraints": ["Public API unchanged"],
  "acceptance": [
    "npm test -- parser.test.ts -t 'trailing comma'",
    {"run": "npm run e2e -- --grep import", "tier": "final"}
  ],
  "approval_required": ["Regenerating snapshots", "Merging the PR"],
  "not_verified": ["Behaviour on Windows"],
  "progress": {"done": [], "remaining": []},
  "decisions": [],
  "lessons": []
}
```

   - `acceptance`: what proves this task, beyond the config's checks
     (don't repeat those). A plain command runs at every stop; one with
     `"tier": "final"` (end-to-end, UI, slow) runs only in the final
     verification. Each must fail until the work is done: write the
     focused test first if there isn't one.
   - `not_verified`: what nothing here can check, agreed now rather than
     discovered in the receipt.
   - `constraints` and `approval_required` come from the ticket and the
     user, not from you. If they don't say and it matters, ask.
5. Check that the acceptance can prove anything: run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify.py" --contract-baseline`.
   A command that already passes doesn't; replace it or say why it stays.
6. For a task with more than a couple of acceptance items, or any UI or
   cross-device behaviour, have the `verifier` agent review the contract
   ("review the contract") and take its changes or say why not.
7. Show the user the objective, scope, constraints, acceptance and
   not_verified in a few lines. If any of it was a guess, ask before
   starting.

Keep `progress`, `decisions` and `lessons` current as you go; they survive
compaction and the next session reads them. Decisions that matter beyond
the task also go wherever the project records them. Delete the file once
the task is finished and its receipt is written.
