#!/usr/bin/env python3
"""SessionStart hook: record the commit the session started from and the
content of anything already uncommitted (the gate checks only what changes
after that), and put the task contract, if any, in front of Claude."""
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (ROOT, STATE, git, is_git_repo, load_config, load_task,  # noqa: E402
                    read_input, snapshot_baseline, write)


def main():
    data = read_input()
    if load_config() is None or not is_git_repo():
        return
    base_path = os.path.join(STATE, "base")
    if data.get("source", "startup") in ("startup", "clear") or not os.path.exists(base_path):
        write(base_path, git("rev-parse", "HEAD").strip())
        write(os.path.join(STATE, "blocks"), "0")
        snapshot_baseline()
    lines = ["Harness active (.claude/harness.json): a Stop gate runs the project's "
             "checks before a turn that changed files can end, and a guard blocks "
             "protected edits. /contract for non-trivial tasks, the verifier agent "
             "before calling it done, /receipt at the end."]
    ignored = subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", ".claude/state/x"])
    if ignored.returncode != 0:
        lines.append("Note: .claude/state/ isn't gitignored; tell the user it should be.")
    task = load_task()
    if task:
        lines.append("Task contract (.claude/state/task.json):\n" + json.dumps(task, indent=2))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
