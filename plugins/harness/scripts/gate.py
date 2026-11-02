#!/usr/bin/env python3
"""Stop hook: Claude can't end a turn that changed the repo until the
fast checks pass: the config's rules, then its fast-tier `checks` whose
`when` matches what changed, then the task contract's fast acceptance
commands (checks.py). Final-tier checks wait for verify.py.

A pass is remembered by a fingerprint of the tree, so a turn that changes
nothing more doesn't run them again. A failure that also happens at the
session's starting commit is logged as pre-existing and doesn't block.
After `gate.max_blocks` failed stops in a row it lets Claude stop and logs
the turn UNVERIFIED.
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (STATE, base, changed_files, is_git_repo, load_config,  # noqa: E402
                    load_task, log, read, read_input, write)
from checks import evaluate, fingerprint  # noqa: E402


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

    entry, failure = evaluate(cfg, b, changed, {"fast"}, load_task())
    entry["kind"] = "gate"
    blocks_path = os.path.join(STATE, "blocks")

    if failure is None:
        write(os.path.join(STATE, "last_pass"), fp)
        write(blocks_path, "0")
        entry["result"] = "PASS" if entry["ran"] > len(entry["preexisting"]) else "NO CHECKS"
        log(entry)
        msgs = []
        if entry["preexisting"]:
            msgs.append("failing at the session's starting commit too, so not blocking: "
                        + ", ".join(entry["preexisting"]))
        if entry["deferred"]:
            msgs.append("final checks wait for verify (/harness:receipt runs them): "
                        + ", ".join(entry["deferred"]))
        if msgs:
            print(json.dumps({"systemMessage": "Harness: " + "; ".join(msgs)}))
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
