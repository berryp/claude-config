---
name: contract
description: Write the task contract (.claude/state/task.json) before a non-trivial change in a project using the harness - a ticket, a feature, a fix touching more than one file - or when the user says /contract or the task's scope changes.
---

The contract turns the request into what "done" means, so the Stop gate
can check it and the verifier can judge against it.

1. Read the ticket or request in full. If the project's instructions say
   where work is tracked (an issue tracker, a tracker doc), read the
   issue there; if that tool isn't connected, say so.
2. Read only enough of the repo to name the scope.
3. Read `.claude/harness.json` to see which checks the gate already runs
   for the paths in scope.
4. Write `.claude/state/task.json`:

```json
{
  "issue": "ABC-123",
  "objective": "One sentence: what must be true when this is done.",
  "scope": ["src/parser/", "docs/format.md"],
  "constraints": ["Public API unchanged"],
  "acceptance": ["npm test -- parser.test.ts -t 'trailing comma'"],
  "approval_required": ["Regenerating snapshots", "Merging the PR"],
  "progress": {"done": [], "remaining": []},
  "decisions": [],
  "lessons": []
}
```

   - `acceptance`: shell commands the gate runs from the repo root after
     the config's checks, so don't repeat those. Add what proves this
     task specifically: a focused test, a CLI run on the case it's about,
     an end-to-end test the config doesn't run every time. Each must exit
     non-zero when the work isn't done. Empty is fine if the config's
     checks are enough.
   - `constraints` and `approval_required` come from the ticket and the
     user, not from you. If they don't say and it matters, ask.
5. Show the user the objective, scope, constraints and acceptance in a
   few lines. If any of it was a guess, ask before starting.

Keep `progress`, `decisions` and `lessons` current as you go; they survive
compaction and the next session reads them. Decisions that matter beyond
the task also go wherever the project records them. Delete the file once
the task is finished and its receipt is written.
