---
name: harness-init
description: Set up the harness plugin in the current project - inspect the repo and write .claude/harness.json (checks, protected paths, rules). Use when the user asks to set up, enable or add the harness, or says /harness-init. Also to revise an existing harness.json after a repeated failure.
disable-model-invocation: true
---

The harness does nothing in a project until `.claude/harness.json` exists.
Your job is to write one that matches how this project is actually built
and checked. Every check and rule must come from something you found in
the repo or the user told you. Don't invent conventions.

## 1. Inspect

Read, don't guess:

- The project's instructions: `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`,
  `docs/development*`. Rules stated there ("update X when you change Y",
  "never edit Z", "run A before pushing") are the main source.
- The task runner and its commands: `mise.toml`, `justfile`, `Makefile`,
  `package.json` scripts, `Taskfile.yml`, `pyproject.toml`, `Cargo.toml`,
  `go.mod`, `Package.swift`, `build.zig`, and so on.
- CI (`.github/workflows/`, `docs/ci/`, `.gitlab-ci.yml`): which checks
  it runs on which paths. Those are the best candidate gate checks.
- Generated or vendored paths: `.gitignore`, "generated"/"do not edit"
  headers, snapshot and golden directories, lockfiles, build output.
- Existing hooks in `.claude/settings.json` that already do some of this
  (don't duplicate them; mention them).
- End-to-end and UI tests: browser automation (Playwright, Puppeteer,
  Cypress), app UI tests (XCUITest, Espresso), integration suites that
  start the real service. Unit tests miss what only shows in a running
  app, so these belong in the harness as final-tier checks.
- Whether the sandbox is on (`sandbox.enabled` in `.claude/settings.json`
  or the user's settings).

## 2. Draft

Write the config against this schema. Omitted keys take the defaults.

```json
{
  "protected_branches": ["main", "master"],
  "confine_writes": true,
  "allow_outside": ["/tmp/", "/private/tmp/", "/private/var/folders/", "~/.claude/"],
  "protect": [
    {"paths": ["snapshots/**"], "decision": "deny",
     "reason": "Generated: run `npm run snap:update` and review the diff."},
    {"paths": ["vendor/**"], "decision": "deny", "gate": true,
     "reason": "Vendored code: update it with `make vendor`, never by hand."}
  ],
  "checks": [
    {"when": ["src/**", "test/**"], "run": "npm run typecheck"},
    {"when": ["src/**", "test/**"], "run": "npm test"},
    {"when": ["docs/**/*.md"], "if_contains": "```mermaid", "run": "npm run check:diagrams"},
    {"when": ["ios/**"], "run": "xcodebuild -scheme App build", "platforms": ["darwin"]},
    {"when": ["src/**", "e2e/**"], "run": "npm run e2e", "tier": "final"}
  ],
  "forbid": [
    {"paths": [".github/workflows/**"], "message": "CI files are the user's to change"}
  ],
  "co_change": [
    {"path": "src/config/schema.ts", "diff_matches": "^[+-].*\\bexport\\b",
     "require": ["docs/config.md"], "message": "Schema changes are documented"}
  ],
  "registered_in": [
    {"new": ["scripts/*.{sh,py}"], "file": "package.json",
     "message": "Every script has an npm script"}
  ],
  "notes": [
    {"when": ["snapshots/**"], "message": "Snapshots changed; review them as behaviour changes"}
  ],
  "verifier_notes": ".claude/harness-verifier.md",
  "gate": {"max_blocks": 3, "check_timeout": 1500, "tail": 60,
           "baseline_check": true, "baseline_setup": "npm ci"}
}
```

Guidance:

- Globs: `*` stays within a path segment, `**` crosses them, `{a,b}`
  alternates, a trailing `/` means everything under it. Paths are
  relative to the repo root.
- `checks` run in the order listed, stopping at the first failure, so
  put the cheapest first: format/lint, typecheck/build, focused tests,
  full tests. Prefer the project's own task names over raw commands.
- `"tier": "final"` is for what's too slow for every stop but needed
  before "done": end-to-end and UI tests, full app builds, install tests.
  They run in the final verification (`/harness:receipt`, the verifier).
  Every project with a UI or a multi-process flow should have at least
  one; if it has none, say so, and suggest the smallest end-to-end test
  that would cover its main flow.
- `platforms` (`darwin`, `linux`, `windows`) is for a check that only
  runs on some machines (Xcode builds, Windows installers). Elsewhere the
  gate skips it and logs it as skipped, rather than failing every turn.
- `protect` is for edits Claude should never make by hand: generated
  files (with the command that regenerates them in `reason`), build
  output, vendored code. Use `"decision": "ask"` for things the user
  might sometimes want edited. The guard can't see every way a script
  writes a file, so for paths that no tool should write in normal work
  either (vendored code, CI config), add `"gate": true`: the gate then
  fails if they change at all. Leave it off for generated files, which
  their generator changes legitimately; flag those with `notes`.
- `forbid` refuses changes at the gate without a guard rule.
- `gate.baseline_check` (on by default): a failing check is re-run at the
  session's starting commit in a temporary worktree, and a failure that
  was already there doesn't block. Set `baseline_setup` to what a fresh
  checkout needs before the checks can run (installing packages), or
  turn `baseline_check` off when that's too slow.
- `co_change` and `registered_in` are for the project's stated "when you
  change X, also update Y" rules. Only add them when the instructions
  state the rule.
- `notes` flag changes that need a human look without failing.

## 3. Confirm and write

Show the user the draft and, for each entry, where it came from (file
and line, or "CI job X"). Ask about anything you weren't sure of. After
they agree:

1. Write `.claude/harness.json`.
2. Add `.claude/state/` to `.gitignore` if it isn't ignored.
3. Create the verifier's calibration notes, `.claude/harness-verifier.md`
   (committed), with a heading and one line saying what it's for: what
   the verifier has missed in this project, each with a short example and
   what would have caught it. Add any known weak spots the user names
   now (say, "the docs drift from the code", "the phone app isn't
   tested").
4. The sandbox. The guard is best-effort: it reads commands, and a
   script can write a file it doesn't recognise. The OS sandbox is the
   enforcement layer, and a plugin can't turn it on. If it isn't on,
   offer to add to `.claude/settings.json`:

   ```json
   {"sandbox": {"enabled": true,
                "filesystem": {"denyWrite": [".github/workflows"]}}}
   ```

   `denyWrite` takes the `"gate": true` and `forbid` paths (not generated
   files, which tools must still write). Network access is then limited
   to allowed domains, so builds that download packages need them in
   `sandbox.network.allowedDomains`, or the command in
   `sandbox.excludedCommands`; check the project's install steps and
   list them. Linux needs `bubblewrap` and `socat`; native Windows has no
   sandbox (WSL2 does). Only with the user's yes.
5. Optionally, add a short paragraph to the project's instructions
   saying the harness is active and naming `/harness:contract`, the
   verifier agent, `/harness:receipt`, `/harness:report` and
   `/harness:garden`.
6. Tell the user the hooks take effect in the next session, and that
   `/harness:report` shows after a couple of weeks which parts earn
   their place.

The config is protected by the harness itself once it exists: later
edits prompt the user.
