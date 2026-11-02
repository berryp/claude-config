#!/usr/bin/env python3
"""PreToolUse hook: the project's protected paths (edits and shell
writes), writes outside the project, pushes to protected branches, force
pushes and skipped git hooks. Denies say what to do instead."""
import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, git, load_config, matches, read_input  # noqa: E402

FORCE = re.compile(r"\bgit\b.*\bpush\b.*(\s--force(?!-with-lease)\b|\s-[a-zA-Z]*f\b)")
NO_VERIFY = re.compile(r"\bgit\b.*--no-verify\b")
REDIRECT = re.compile(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*['\"]?([^\s'\";|&]+)")
LAST_ARG_WRITERS = ("cp", "mv", "truncate", "install", "rsync")
SEGMENTS = re.compile(r"&&|\|\||;|\|")
# A script run inline (python -c, a heredoc, node -e, perl -i ...) that
# looks like it writes files. The guard can't parse it, so a protected path
# named in it is asked about rather than allowed; the gate's "gate": true
# rules and forbid catch what still gets through.
INLINE_SCRIPT = re.compile(
    r"\b(python[0-9.]*|node|deno|bun|ruby|perl|php)\b[^|;&]*?(\s-[ceEi]\b|\s-\s|<<)")
WRITES = re.compile(
    r"open\([^)]*['\"][wax+]|\.write(_text|_bytes|FileSync|File)?\(|json\.dump\(|"
    r"shutil\.|os\.(replace|rename|remove|unlink)|\bunlink(Sync)?\(|\brename(Sync)?\(|"
    r"copyFile|\bFile\.(write|open)|\s-p?i\b")
PATHISH = re.compile(r"[A-Za-z0-9_.@~/{}-]*[/.][A-Za-z0-9_.@~/{}-]+")


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def rel(path):
    p = os.path.realpath(os.path.join(ROOT, os.path.expanduser(path)))
    root = os.path.realpath(ROOT)
    if p == root or p.startswith(root + os.sep):
        return os.path.relpath(p, root)
    return None


def check_path(cfg, path):
    r = rel(path)
    if r is None:
        if cfg["confine_writes"]:
            p = os.path.realpath(os.path.expanduser(path))
            allowed = tuple(os.path.expanduser(a) for a in cfg["allow_outside"])
            if not p.startswith(allowed):
                decide("deny", "Outside the project (%s). Work inside it." % path)
        return
    for rule in cfg["protect"]:
        if matches(r, rule["paths"]):
            decide(rule.get("decision", "deny"), rule.get("reason", "Protected path."))


def write_targets(cmd):
    """Paths a shell command writes: redirect and tee targets, the files
    `sed -i` edits, and the destination of cp/mv and friends."""
    targets = REDIRECT.findall(cmd)
    for seg in SEGMENTS.split(cmd):
        words = seg.split()
        if not words:
            continue
        if words[0] == "sed" and any(w.startswith("-i") for w in words[1:]):
            targets += [w for w in words[2:] if not w.startswith("-")][1:]
        elif words[0] in LAST_ARG_WRITERS and len(words) > 2:
            targets.append(words[-1])
    return [t.strip("'\"") for t in targets if not t.startswith("/dev/")]


def pushes_protected(cfg, cmd):
    branches = cfg["protected_branches"]
    if not branches:
        return None
    current = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    for seg in SEGMENTS.split(cmd):
        words = seg.split()
        if words[:2] != ["git", "push"]:
            continue
        args = [w for w in words[2:] if not w.startswith("-")]
        refs = args[1:]
        if not refs and current in branches:
            return current
        for ref in refs:
            dest = ref.split(":")[-1].lstrip("+")
            dest = dest[len("refs/heads/"):] if dest.startswith("refs/heads/") else dest
            if dest in branches or (dest == "HEAD" and current in branches):
                return dest
    return None


def check_bash(cfg, cmd):
    if FORCE.search(cmd):
        decide("deny", "No force pushes. Push a new commit, or ask the user.")
    branch = pushes_protected(cfg, cmd)
    if branch:
        decide("deny", "Don't push to %s: push a branch and open a PR." % branch)
    if NO_VERIFY.search(cmd):
        decide("deny", "Don't skip git hooks; fix what they catch.")
    for target in write_targets(cmd):
        if rel(target) is not None:
            check_path(cfg, target)
    if INLINE_SCRIPT.search(cmd) and WRITES.search(cmd):
        for token in set(PATHISH.findall(cmd)):
            r = rel(token.strip("'\""))
            if r is None:
                continue
            for rule in cfg["protect"]:
                if matches(r, rule["paths"]):
                    decide("ask", "This inline script seems to write %s, which is protected: "
                                  "%s" % (r, rule.get("reason", "")))


def main():
    data = read_input()
    cfg = load_config()
    if cfg is None:
        return
    tool = data.get("tool_name", "")
    args = data.get("tool_input", {}) or {}
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = args.get("file_path") or args.get("notebook_path")
        if path:
            check_path(cfg, path)
    elif tool == "Bash":
        check_bash(cfg, args.get("command", ""))


if __name__ == "__main__":
    main()
