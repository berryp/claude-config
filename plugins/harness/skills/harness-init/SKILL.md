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

## 2. Draft

Write the config against this schema. Omitted keys take the defaults.

```json
{
  "protected_branches": ["main", "master"],
  "confine_writes": true,
  "allow_outside": ["/tmp/", "/private/tmp/", "/private/var/folders/", "~/.claude/"],
  "protect": [
    {"paths": ["snapshots/**"], "decision": "deny",
     "reason": "Generated: run `npm run snap:update` and review the diff."}
  ],
  "checks": [
    {"when": ["src/**", "test/**"], "run": "npm run typecheck"},
    {"when": ["src/**", "test/**"], "run": "npm test"},
    {"when": ["docs/**/*.md"], "if_contains": "```mermaid", "run": "npm run check:diagrams"}
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
  "gate": {"max_blocks": 3, "check_timeout": 1500, "tail": 60}
}
```

Guidance:

- Globs: `*` stays within a path segment, `**` crosses them, `{a,b}`
  alternates, a trailing `/` means everything under it. Paths are
  relative to the repo root.
- `checks` run in the order listed, stopping at the first failure, so
  put the cheapest first: format/lint, typecheck/build, focused tests,
  full tests. Prefer the project's own task names over raw commands.
  Leave out anything slow and occasional (end-to-end, release builds);
  a task contract can add those when a task needs them.
- `protect` is for edits Claude should never make by hand: generated
  files (with the command that regenerates them in `reason`), build
  output, vendored code. Use `"decision": "ask"` for things the user
  might sometimes want edited.
- `forbid` catches what slips past `protect` (a shell command, a
  generated step) at the gate.
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
3. Optionally, add a short paragraph to the project's instructions
   saying the harness is active and naming `/contract`, the verifier
   agent and `/receipt`.
4. Tell the user the hooks take effect in the next session.

The config is protected by the harness itself once it exists: later
edits prompt the user.
