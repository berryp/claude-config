#!/usr/bin/env python3
"""Stop hook: Claude can't end a turn that changed the repo until the
checks pass. In order: the config's `forbid`, `co_change` and
`registered_in` rules, the `checks` whose `when` matches what changed
(skipping, and logging, those whose `platforms` exclude this one),
then the task contract's own `acceptance` commands
(.claude/state/task.json). A contract adds checks; it can't replace the
config's.

A pass is remembered by a fingerprint of the tree, so a turn that changes
nothing more doesn't run them again. After `gate.max_blocks` failed stops
in a row it lets Claude stop and logs the turn UNVERIFIED.
"""
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (ROOT, STATE, added_files, base, changed_files,  # noqa: E402
                    content_hashes, git, is_git_repo, load_config, load_task, log, matches, read,
                    read_input, untracked, write)


def fingerprint(b):
    h = hashlib.sha256()
    h.update(git("rev-parse", "HEAD").encode())
    h.update(git("diff", "--binary", b).encode())
    for name, blob in sorted(content_hashes(untracked()).items()):
        h.update(("%s %s\n" % (name, blob)).encode())
    return h.hexdigest()


def selected_checks(cfg, changed):
    """The checks for what changed, and those of them that can't run on
    this platform (skipped, and logged as such)."""
    out, skipped = [], []
    here = platform.system().lower()  # darwin, linux, windows
    for c in cfg["checks"]:
        hit = changed if "when" not in c else [f for f in changed if matches(f, c["when"])]
        if c.get("if_contains"):
            hit = [f for f in hit if c["if_contains"] in read(os.path.join(ROOT, f))]
        if not hit or c["run"] in out or c["run"] in skipped:
            continue
        if c.get("platforms") and here not in c["platforms"]:
            skipped.append(c["run"])
        else:
            out.append(c["run"])
    return out, skipped


def rule_failures(cfg, b, changed):
    out = []
    for r in cfg["forbid"]:
        hit = [f for f in changed if matches(f, r["paths"])]
        if hit:
            out.append("%s (%s)" % (r.get("message", "These files may not change"),
                                    ", ".join(hit)))
    for r in cfg["co_change"]:
        for f in [f for f in changed if matches(f, [r["path"]])]:
            diff = git("diff", b, "--", f) or read(os.path.join(ROOT, f))
            if re.search(r["diff_matches"], diff, re.M):
                missing = [x for x in r["require"] if x not in changed]
                if missing:
                    out.append("%s (%s changed, %s didn't)" % (
                        r.get("message", "These files change together"), f,
                        " and ".join(missing)))
    for r in cfg["registered_in"]:
        text = read(os.path.join(ROOT, r["file"]))
        for f in added_files(b):
            if matches(f, r["new"]) and os.path.basename(f) not in text:
                out.append("%s (%s isn't mentioned in %s)" % (
                    r.get("message", "New file isn't registered"), f, r["file"]))
    return out


def notes(cfg, changed):
    out = []
    for n in cfg["notes"]:
        hit = [f for f in changed if matches(f, n["when"])]
        if hit:
            out.append("%s: %s" % (n["message"], ", ".join(hit)))
    return out


def run(cmd, timeout):
    t = time.time()
    try:
        r = subprocess.run(["bash", "-lc", cmd], cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout)
        rc, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        partial = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        rc, out = 124, "timed out after %ds\n%s" % (timeout, partial)
    return rc, out, round(time.time() - t, 1)


def main():
    read_input()
    cfg = load_config()
    if cfg is None or not is_git_repo():
        return
    g = cfg["gate"]
    b = base()
    changed = changed_files(b)
    if not changed:
        return
    fp = fingerprint(b)
    if fp == read(os.path.join(STATE, "last_pass")):
        return

    checks, skipped = selected_checks(cfg, changed)
    task = load_task() or {}
    extra = [c for c in task.get("acceptance", []) if c not in checks]
    checks += extra

    results, failure = [], None
    rules = rule_failures(cfg, b, changed)
    if rules:
        failure = "Project rules:\n- " + "\n- ".join(rules)
    else:
        for cmd in checks:
            rc, out, secs = run(cmd, g["check_timeout"])
            results.append({"cmd": cmd, "rc": rc, "secs": secs})
            if rc != 0:
                tail = "\n".join(out.rstrip().splitlines()[-g["tail"]:])
                failure = "`%s` failed (exit %d):\n%s" % (cmd, rc, tail)
                break

    blocks_path = os.path.join(STATE, "blocks")
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "source": "config+contract" if extra else "config",
             "checks": results, "skipped": skipped, "rules": rules, "changed": changed,
             "notes": notes(cfg, changed)}

    if failure is None:
        write(os.path.join(STATE, "last_pass"), fp)
        write(blocks_path, "0")
        entry["result"] = "PASS" if checks else "NO CHECKS"
        log(entry)
        return

    blocks = int(read(blocks_path, "0") or 0) + 1
    if blocks >= g["max_blocks"]:
        write(blocks_path, "0")
        entry["result"] = "UNVERIFIED"
        log(entry)
        print(json.dumps({"systemMessage":
              "Harness: checks still failing after %d attempts; stopping UNVERIFIED. "
              "See .claude/state/gate.log." % g["max_blocks"]}))
        return

    write(blocks_path, str(blocks))
    entry["result"] = "BLOCKED"
    log(entry)
    print(json.dumps({"decision": "block", "reason":
          "Not done: the harness's checks fail (attempt %d of %d). Fix the cause, not "
          "the check; if a check or rule is wrong, say so and stop instead.\n\n%s"
          % (blocks, g["max_blocks"], failure)}))


if __name__ == "__main__":
    main()
