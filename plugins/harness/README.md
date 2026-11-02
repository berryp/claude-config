# harness

A per-project agent harness for Claude Code, after the "harness
engineering" idea: put the rules that matter in the environment, not the
prompt. It does nothing in a project until that project has
`.claude/harness.json`, so it is safe to install for every project.

## What it does

- **Stop gate.** Before Claude can end a turn that changed files, it runs
  the project's rules and checks: `forbid`, `co_change`, `registered_in`,
  then each entry in `checks` whose `when` globs match what changed
  (cheapest first), then the task contract's `acceptance` commands. A
  check limited by `platforms` is skipped elsewhere and logged as
  skipped. On a
  failure the turn continues with the failing output. A tree that already
  passed isn't checked again. After `gate.max_blocks` failures in a row
  it lets Claude stop and logs the turn UNVERIFIED.
- **Guard (PreToolUse).** Blocks or asks about edits to `protect` paths,
  including shell writes to them (redirects, `tee`, `sed -i`, `cp`/`mv`);
  writes outside the project (`confine_writes`); pushes to
  `protected_branches`, including a bare `git push` from one; force
  pushes; and `--no-verify`. `.claude/harness.json` itself always asks.
- **Session start.** Records the starting commit, so work committed
  mid-session is still checked, and the content of anything already
  uncommitted or untracked, so the gate ignores it unless it changes.
  Shows Claude the current task contract.
- **`/harness:contract`** writes `.claude/state/task.json`: objective,
  scope, constraints, extra acceptance commands, approvals, progress.
- **`verifier` agent.** Read-only; tries to reject the finished change
  against the contract, the project's rules and the gate log.
- **`/harness:receipt`** summarises what changed, what the gate verified
  and what it didn't, decisions, risks, approvals still needed.
- **`/harness:harness-init`** inspects a repo and drafts its
  `.claude/harness.json` with you.

State lives in `.claude/state/` (gitignore it): `base`, `task.json`,
`baseline.json`, `gate.log` (one JSON line per gate run), `last_pass`, `blocks`.

## Use

1. Install: `/plugin install harness@berryp`.
2. In a project, `/harness:harness-init`, review the draft, then start a
   new session.
3. Per task: `/harness:contract`, work, "run the verifier",
   `/harness:receipt`.

To pause it in a project, set `"enabled": false` in `harness.json`.

## Config

See the schema in `skills/harness-init/SKILL.md` and a full example in
`examples/stagedisplay.json`. Globs: `*` within a segment, `**` across,
`{a,b}` alternatives, trailing `/` for a whole directory.

Requires `python3` (3.9+, stdlib only), `git` and `bash`.
