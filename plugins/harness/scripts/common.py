"""Shared by the harness hooks: the project, its config, its state, git,
and path globs.

Everything is driven by <project>/.claude/harness.json. Without it every
hook exits at once, so the plugin can be installed everywhere and only
acts in projects that opt in.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
CONFIG = os.path.join(ROOT, ".claude", "harness.json")
STATE = os.path.join(ROOT, ".claude", "state")
TASK = os.path.join(STATE, "task.json")
BASELINE = os.path.join(STATE, "baseline.json")
LOG = os.path.join(STATE, "gate.log")

DEFAULTS = {
    # Branches Claude may not push to directly.
    "protected_branches": ["main", "master"],
    # Deny writes outside the project, except under these prefixes.
    "confine_writes": True,
    "allow_outside": ["/tmp/", "/private/tmp/", "/private/var/folders/", "~/.claude/"],
    # Edits and shell writes: [{"paths": [glob], "decision": "deny"|"ask", "reason": str}]
    "protect": [],
    # Stop-gate checks, run in order (cheapest first) when a changed file
    # matches `when` (omit `when` to run on any change). `if_contains`
    # narrows it to changed files containing that text; `platforms`
    # ("darwin", "linux", "windows") limits where it can run.
    # [{"run": cmd, "when": [glob], "if_contains": str, "platforms": [str]}]
    "checks": [],
    # Changes the gate refuses outright: [{"paths": [glob], "message": str}]
    "forbid": [],
    # If a file's diff matches `diff_matches`, the `require` files must
    # change too: [{"path": glob, "diff_matches": regex, "require": [path], "message": str}]
    "co_change": [],
    # New files matching `new` must be mentioned by name in `file`:
    # [{"new": [glob], "file": path, "message": str}]
    "registered_in": [],
    # Not failures; flagged in the gate log for the receipt:
    # [{"when": [glob], "message": str}]
    "notes": [],
    "gate": {"max_blocks": 3, "check_timeout": 1500, "tail": 60},
}

# Always protected once a project opts in: the harness's own config.
BUILTIN_PROTECT = [
    {"paths": [".claude/harness.json"], "decision": "ask",
     "reason": "This changes the harness that checks your work. The user decides."},
]


def load_config():
    """The project's config merged over the defaults, or None to opt out."""
    try:
        with open(CONFIG) as f:
            user = json.load(f)
    except OSError:
        return None
    except ValueError as e:
        print("harness: .claude/harness.json is not valid JSON (%s); hooks disabled." % e,
              file=sys.stderr)
        return None
    if user.get("enabled") is False:
        return None
    cfg = dict(DEFAULTS)
    cfg.update(user)
    cfg["gate"] = dict(DEFAULTS["gate"], **user.get("gate", {}))
    cfg["protect"] = BUILTIN_PROTECT + list(cfg["protect"])
    return cfg


def read_input():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def git(*args):
    r = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def is_git_repo():
    return git("rev-parse", "--is-inside-work-tree").strip() == "true"


def load_task():
    try:
        with open(TASK) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def base():
    """The commit the session started from (SessionStart records it)."""
    b = read(os.path.join(STATE, "base"))
    if b and git("cat-file", "-t", b).strip() == "commit":
        return b
    return git("rev-parse", "HEAD").strip()


def untracked():
    return git("ls-files", "--others", "--exclude-standard").split()


def content_hashes(paths):
    """Blob hash of each path's current content, or "deleted"."""
    present = [p for p in paths if os.path.isfile(os.path.join(ROOT, p))]
    out = {p: "deleted" for p in paths}
    if present:
        r = subprocess.run(["git", "-C", ROOT, "hash-object", "--stdin-paths"],
                           input="\n".join(present) + "\n", capture_output=True, text=True)
        hashes = r.stdout.split()
        if len(hashes) == len(present):
            out.update(zip(present, hashes))
    return out


def dirty():
    """Uncommitted (staged, unstaged) and untracked paths right now."""
    return sorted(set(git("diff", "--name-only", "HEAD").split()) | set(untracked()))


def snapshot_baseline():
    """At session start: the content of everything already dirty or
    untracked, so the gate only counts what changes after it."""
    write(BASELINE, json.dumps(content_hashes(dirty())))


def _unchanged_since_start(names):
    try:
        with open(BASELINE) as f:
            baseline = json.load(f)
    except (OSError, ValueError):
        return set()
    known = [n for n in names if n in baseline]
    now = content_hashes(known)
    return {n for n in known if now[n] == baseline[n]}


def changed_files(b):
    """Changed since the session started: committed, staged, unstaged and
    untracked, minus files whose content is what it was at session start,
    and minus the harness's own state."""
    names = set(git("diff", "--name-only", b).split()) | set(untracked())
    names = {n for n in names if not n.startswith(".claude/state/")}
    return sorted(names - _unchanged_since_start(names))


def added_files(b):
    names = set(git("diff", "--name-only", "--diff-filter=A", b).split()) | set(untracked())
    return sorted(names - _unchanged_since_start(names))


def log(entry):
    os.makedirs(STATE, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# Globs: `*` and `?` stay within a path segment, `**` crosses them, `{a,b}`
# alternates, and a trailing `/` means everything under that directory.

def _braces(g):
    m = re.search(r"\{([^{}]*)\}", g)
    if not m:
        return [g]
    out = []
    for alt in m.group(1).split(","):
        out += _braces(g[:m.start()] + alt + g[m.end():])
    return out


def _glob_re(g):
    if g.endswith("/"):
        g += "**"
    out, i = "", 0
    while i < len(g):
        if g.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif g.startswith("**", i):
            out, i = out + ".*", i + 2
        elif g[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif g[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(g[i]), i + 1
    return re.compile("^" + out + "$")


_cache = {}


def matches(path, globs):
    for g in globs or []:
        for alt in _braces(g):
            r = _cache.get(alt)
            if r is None:
                r = _cache[alt] = _glob_re(alt)
            if r.match(path):
                return True
    return False
