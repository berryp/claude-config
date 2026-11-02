# harness

A per-project agent harness for Claude Code, after the "harness
engineering" idea: put the rules that matter in the environment, not the
prompt. It does nothing in a project until that project has
`.claude/harness.json`, so it is safe to install for every project.

## What it does

- **Stop gate.** Before Claude can end a turn that changed files, it runs
  the project's rules (`forbid`, `co_change`, `registered_in`, and
  `protect` rules marked `"gate": true`), then each fast-tier check whose
  `when` globs match what changed (cheapest first), then the task
  contract's fast acceptance commands. On a failure the turn continues
  with the failing output. A tree that already passed isn't checked
  again. After `gate.max_blocks` failures in a row it lets Claude stop and
  logs the turn UNVERIFIED.
- **Pre-existing failures don't block.** A failing check is re-run at the
  session's starting commit in a temporary worktree; if it fails there
  too, it's logged as pre-existing and the turn isn't blocked for it.
  Contract checks aren't compared: they're meant to fail before the work.
- **Two tiers.** `"tier": "final"` checks (end-to-end, UI, slow builds)
  don't run at every stop; they run in the final verification
  (`scripts/verify.py`), which `/harness:receipt` and the verifier run
  before the task is called done. A check limited by `platforms` is
  skipped elsewhere and logged as skipped.
- **Guard (PreToolUse).** Blocks or asks about edits to `protect` paths,
  including shell writes to them (redirects, `tee`, `sed -i`, `cp`/`mv`)
  and inline scripts that look like they write them (`python -c`,
  heredocs, `node -e`, `perl -i`); writes outside the project
  (`confine_writes`); pushes to `protected_branches`, including a bare
  `git push` from one; force pushes; and `--no-verify`.
  `.claude/harness.json` itself always asks. The guard is best-effort:
  the gate's `"gate": true` rules and Claude Code's sandbox
  (`/harness:harness-init` offers to set it up) are what enforce.
- **Session start.** Records the starting commit, so work committed
  mid-session is still checked, and the content of anything already
  uncommitted or untracked, so the gate ignores it unless it changes.
  Shows Claude the current task contract.
- **`/harness:contract`** writes `.claude/state/task.json` (objective,
  scope, constraints, acceptance, what can't be verified, approvals,
  progress), checks that each acceptance command fails before the work
  (`verify.py --contract-baseline`), and has the verifier review it.
- **`verifier` agent.** Read-only; reviews contracts before the work, and
  tries to reject finished work: runs the final verification, checks the
  project's calibration notes (`.claude/harness-verifier.md`: what
  verifiers have missed here before), and needs evidence and recorded
  attempts to accept.
- **`/harness:receipt`** runs the final verification and the verifier,
  records the verdict, and summarises what changed, what was verified
  and what wasn't, decisions, risks and approvals still needed.
- **`/harness:report`** reads the gate log: stops, first-pass rate, time
  per stop, what each check and rule caught, verifier verdicts, and which
  parts are candidates to remove or retune.
- **`/harness:garden`** runs the read-only `gardener` agent: docs that
  don't match the code, stale instructions, prose rules that could be
  checks, harness parts that never fire, leftovers.
- **`/harness:harness-init`** inspects a repo and drafts its
  `.claude/harness.json`, the calibration notes and the sandbox settings
  with you.

State lives in `.claude/state/` (gitignore it): `base`, `task.json`,
`baseline.json`, `baseline_results.json`, `gate.log` (one JSON line per
gate run, verify run and verdict), `last_pass`, `last_verify`, `blocks`.

## Use

1. Install: `/plugin install harness@berryp`.
2. In a project, `/harness:harness-init`, review the draft, then start a
   new session.
3. Per task: `/harness:contract`, work, `/harness:receipt`.
4. Now and then: `/harness:report` (is each part earning its place?) and
   `/harness:garden` (drift).

To pause it in a project, set `"enabled": false` in `harness.json`.

## Config

See the schema in `skills/harness-init/SKILL.md` and a full example in
`examples/stagedisplay.json`. Globs: `*` within a segment, `**` across,
`{a,b}` alternatives, trailing `/` for a whole directory.

Requires `python3` (3.9+, stdlib only), `git` and `bash`.
