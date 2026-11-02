---
name: report
description: Report what the harness has done in this project - stops checked, first-pass rate, time per stop, which checks and rules caught anything, verifier verdicts - and which parts are candidates to remove or retune. Use when the user says /harness:report or asks whether the harness is worth it, slow, or due a cleanup.
---

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/report.py"` (add
   `--days 14` for a recent window, `--json` for the raw numbers).
2. Tell the user, in a few lines:
   - Whether the gate is earning its time: the first-pass rate, how many
     changes it sent back, and the mean and worst time per stop.
   - The checks and rules that caught real problems, and the slowest ones.
   - The candidates the report lists. A check that never failed in 10+
     runs may be redundant, or may guard something that rarely breaks but
     matters, so say which you think it is and why. A check that never ran
     usually has a wrong `when`.
   - Pre-existing failures that keep recurring: something on the main
     branch is broken.
3. Propose concrete changes to `.claude/harness.json` (move a slow check
   to `"tier": "final"`, narrow a `when`, remove a check). Don't make them
   without the user's yes; the file is theirs to approve.

The log only covers sessions on this machine (`.claude/state/` isn't
committed), so say how much history it holds.
