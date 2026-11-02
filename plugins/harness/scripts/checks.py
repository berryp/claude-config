"""Running the project's rules and checks, shared by the Stop gate
(gate.py) and the full verification (verify.py).

Checks have a tier: "fast" (the default) runs at every stop that changed
what it covers; "final" (end-to-end, UI, slow builds) runs only in
verify.py, before the task is called done. A check whose `platforms`
exclude this machine is skipped and logged as skipped.

A check that fails is run again at the session's starting commit, in a
temporary worktree. If it fails there too, the failure was there before
the session and doesn't block (it is logged as pre-existing).
"""
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time

from common import (ROOT, STATE, added_files, content_hashes, git, matches, read,
                    untracked, write)

BASE_RESULTS = os.path.join(STATE, "baseline_results.json")


def fingerprint(b):
    h = hashlib.sha256()
    h.update(git("rev-parse", "HEAD").encode())
    h.update(git("diff", "--binary", b).encode())
    for name, blob in sorted(content_hashes(untracked()).items()):
        h.update(("%s %s\n" % (name, blob)).encode())
    return h.hexdigest()


def contract_checks(task):
    """The task contract's acceptance commands as checks. An entry is a
    command (tier fast) or {"run": cmd, "tier": "final"}."""
    out = []
    for a in (task or {}).get("acceptance", []):
        c = {"run": a} if isinstance(a, str) else dict(a)
        c["contract"] = True
        out.append(c)
    return out


def select(cfg, changed, tiers, task=None):
    """The checks to run for what changed, in order, and the ones left out:
    `skipped` (not runnable on this platform) and `deferred` (a tier not
    being run now)."""
    here = platform.system().lower()  # darwin, linux, windows
    run, skipped, deferred, seen = [], [], [], set()
    for c in list(cfg["checks"]) + contract_checks(task):
        if c["run"] in seen:
            continue
        if not c.get("contract"):
            hit = changed if "when" not in c else [f for f in changed if matches(f, c["when"])]
            if c.get("if_contains"):
                hit = [f for f in hit if c["if_contains"] in read(os.path.join(ROOT, f))]
            if not hit:
                continue
        seen.add(c["run"])
        if c.get("tier", "fast") not in tiers:
            deferred.append(c["run"])
        elif c.get("platforms") and here not in c["platforms"]:
            skipped.append(c["run"])
        else:
            run.append(c)
    return run, skipped, deferred


def rule_failures(cfg, b, changed):
    out = []
    for r in cfg["protect"]:
        # The guard stops edits it can see; this catches the ones it can't
        # (a script, a generator run by hand) for rules marked "gate".
        if r.get("gate"):
            hit = [f for f in changed if matches(f, r["paths"])]
            if hit:
                out.append("%s (%s)" % (r.get("reason", "Protected path changed"),
                                        ", ".join(hit)))
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


def run(cmd, timeout, cwd=ROOT):
    t = time.time()
    env = dict(os.environ, CLAUDE_PROJECT_DIR=cwd)
    try:
        r = subprocess.run(["bash", "-lc", cmd], cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=timeout)
        rc, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        partial = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        rc, out = 124, "timed out after %ds\n%s" % (timeout, partial)
    return rc, out, round(time.time() - t, 1)


def fails_at_base(cmd, b, g):
    """Whether `cmd` also fails at commit `b`: True, False, or None when it
    can't be told (no worktree, or the setup failed). Cached per commit."""
    if not g.get("baseline_check", True):
        return None
    try:
        with open(BASE_RESULTS) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    known = cache.get(b, {})
    if cmd in known:
        return known[cmd]
    tmp = tempfile.mkdtemp(prefix="harness-base-")
    answer = None
    try:
        r = subprocess.run(["git", "-C", ROOT, "worktree", "add", "--detach", "-f", tmp, b],
                           capture_output=True, text=True)
        if r.returncode == 0:
            setup_ok = True
            if g.get("baseline_setup"):
                setup_ok = run(g["baseline_setup"], g["check_timeout"], tmp)[0] == 0
            if setup_ok:
                rc = run(cmd, g["check_timeout"], tmp)[0]
                # Not found / not runnable / timed out there says nothing
                # about the code, only that the checkout isn't set up.
                answer = None if rc in (124, 126, 127) else rc != 0
    finally:
        subprocess.run(["git", "-C", ROOT, "worktree", "remove", "--force", tmp],
                       capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)
        subprocess.run(["git", "-C", ROOT, "worktree", "prune"], capture_output=True)
    if answer is not None:
        cache = {b: dict(known, **{cmd: answer})}  # only the current base is kept
        write(BASE_RESULTS, json.dumps(cache))
    return answer


def evaluate(cfg, b, changed, tiers, task=None):
    """Rules, then the selected checks in order. Returns the log entry
    (without result) and the failure text, or None if nothing failed
    that this session caused."""
    g = cfg["gate"]
    t0 = time.time()
    checks, skipped, deferred = select(cfg, changed, tiers, task)
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "base": b,
             "checks": [], "skipped": skipped, "deferred": deferred,
             "preexisting": [], "rules": [], "changed": changed,
             "notes": notes(cfg, changed)}
    failure = None
    rules = rule_failures(cfg, b, changed)
    entry["rules"] = rules
    if rules:
        failure = "Project rules:\n- " + "\n- ".join(rules)
    else:
        for c in checks:
            rc, out, secs = run(c["run"], g["check_timeout"])
            res = {"cmd": c["run"], "rc": rc, "secs": secs}
            if c.get("contract"):
                res["contract"] = True
            entry["checks"].append(res)
            if rc == 0:
                continue
            # A contract check is meant to fail before the work, so only the
            # config's checks are compared with the starting commit.
            if not c.get("contract") and fails_at_base(c["run"], b, g):
                res["preexisting"] = True
                entry["preexisting"].append(c["run"])
                continue
            tail = "\n".join(out.rstrip().splitlines()[-g["tail"]:])
            failure = "`%s` failed (exit %d):\n%s" % (c["run"], rc, tail)
            break
    entry["ran"] = len(entry["checks"])
    entry["secs"] = round(time.time() - t0, 1)
    return entry, failure
