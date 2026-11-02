#!/usr/bin/env python3
"""The full verification, run before a task is called done (the receipt
and the verifier run it): the rules and every check that covers what
changed, final tier included, plus all of the task contract's acceptance
commands. Prints a summary, logs it, and exits 1 if anything this session
caused fails.

  verify.py                     verify the work
  verify.py --contract-baseline run only the contract's acceptance commands,
                                before the work: one that already passes
                                doesn't prove anything about the task
"""
import time
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (STATE, base, changed_files, is_git_repo, load_config,  # noqa: E402
                    load_task, log, write)
from checks import contract_checks, evaluate, fingerprint, run  # noqa: E402


def contract_baseline(cfg):
    task = load_task()
    if not task or not task.get("acceptance"):
        print("No task contract with acceptance commands (.claude/state/task.json).")
        return 1
    weak = []
    for c in contract_checks(task):
        rc, _, secs = run(c["run"], cfg["gate"]["check_timeout"])
        print("%s  %s (%.1fs)" % ("passes already" if rc == 0 else "fails (good)  ",
                                  c["run"], secs))
        if rc == 0:
            weak.append(c["run"])
    log({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "contract-baseline", "acceptance": [c["run"] for c in contract_checks(task)],
         "already_passing": weak})
    if weak:
        print("\nThese pass before the work, so they can't show it's done. Make each fail "
              "until the task is done (a focused test for the new behaviour), or say why "
              "it's there.")
        return 1
    return 0


def main():
    cfg = load_config()
    if cfg is None or not is_git_repo():
        print("The harness isn't active here (no .claude/harness.json).")
        return 1
    if "--contract-baseline" in sys.argv:
        return contract_baseline(cfg)
    b = base()
    changed = changed_files(b)
    entry, failure = evaluate(cfg, b, changed, {"fast", "final"}, load_task())
    entry["kind"] = "verify"
    entry["result"] = ("FAIL" if failure else
                       "PASS" if entry["ran"] > len(entry["preexisting"]) else "NO CHECKS")
    log(entry)
    if entry["result"] == "PASS":
        write(os.path.join(STATE, "last_verify"), fingerprint(b))

    print("VERIFY %s  (%d checks, %.1fs)" % (entry["result"], entry["ran"], entry["secs"]))
    for c in entry["checks"]:
        state = "pre-existing" if c.get("preexisting") else ("ok" if c["rc"] == 0 else "FAIL")
        print("  %-12s %s (%.1fs)" % (state, c["cmd"], c["secs"]))
    for s in entry["skipped"]:
        print("  %-12s %s (not runnable on this platform)" % ("skipped", s))
    for r in entry["rules"]:
        print("  %-12s %s" % ("rule", r))
    for n in entry["notes"]:
        print("  %-12s %s" % ("note", n))
    if failure:
        print("\n" + failure)
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
