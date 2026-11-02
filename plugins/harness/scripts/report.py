#!/usr/bin/env python3
"""What the harness has done in this project, from .claude/state/gate.log,
so its parts can be kept, tuned or deleted on evidence.

  report.py                  the report (all of the log)
  report.py --days 14        only the last 14 days
  report.py --json           the same as JSON
  report.py --verdict ACCEPT record the verifier's verdict (or REJECT)
"""
import json
import os
import sys
import time
from collections import defaultdict

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import LOG, load_config, log  # noqa: E402


def entries(days=None):
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400)) if days else ""
    out = []
    try:
        with open(LOG) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("time", "") >= cutoff:
                    out.append(e)
    except OSError:
        pass
    return out


def summarise(es, cfg):
    gates = [e for e in es if e.get("kind", "gate") == "gate"]
    verifies = [e for e in es if e.get("kind") == "verify"]
    verdicts = [e for e in es if e.get("kind") == "verdict"]
    results = defaultdict(int)
    for e in gates:
        results[e.get("result", "?")] += 1

    # A "change" is a run of gate entries ending in PASS or UNVERIFIED.
    # First-pass: the first stop of the change already passed.
    changes, first_pass, streak = 0, 0, 0
    for e in gates:
        streak += 1
        if e.get("result") in ("PASS", "NO CHECKS", "UNVERIFIED"):
            changes += 1
            if streak == 1 and e.get("result") != "UNVERIFIED":
                first_pass += 1
            streak = 0

    per_check = defaultdict(lambda: {"runs": 0, "failed": 0, "preexisting": 0,
                                     "secs": 0.0, "skipped": 0})
    for e in gates + verifies:
        for c in e.get("checks", []):
            p = per_check[c["cmd"]]
            p["runs"] += 1
            p["secs"] += c.get("secs", 0)
            if c.get("preexisting"):
                p["preexisting"] += 1
            elif c.get("rc", 0) != 0:
                p["failed"] += 1
        for s in e.get("skipped", []):
            per_check[s]["skipped"] += 1

    rule_hits = defaultdict(int)
    for e in gates + verifies:
        for r in e.get("rules", []):
            rule_hits[r.split(" (")[0]] += 1

    gate_secs = [e.get("secs", 0) for e in gates if "secs" in e]
    configured = [c["run"] for c in (cfg or {}).get("checks", [])]
    rules = ([r.get("message", "") for r in (cfg or {}).get("forbid", [])] +
             [r.get("message", "") for r in (cfg or {}).get("co_change", [])] +
             [r.get("message", "") for r in (cfg or {}).get("registered_in", [])])
    never_failed = [c for c in configured
                    if per_check[c]["runs"] >= 10 and per_check[c]["failed"] == 0]
    never_ran = [c for c in configured if per_check[c]["runs"] == 0 and not per_check[c]["skipped"]]
    rules_never = [r for r in rules if r and rule_hits.get(r, 0) == 0]

    return {
        "stops": len(gates), "results": dict(results), "changes": changes,
        "first_pass_rate": round(first_pass / changes, 2) if changes else None,
        "unverified": results.get("UNVERIFIED", 0),
        "gate_secs_mean": round(sum(gate_secs) / len(gate_secs), 1) if gate_secs else None,
        "gate_secs_max": max(gate_secs) if gate_secs else None,
        "verify_runs": len(verifies),
        "verify_failed": sum(1 for e in verifies if e.get("result") == "FAIL"),
        "verdicts": {v: sum(1 for e in verdicts if e.get("verdict") == v)
                     for v in ("ACCEPT", "REJECT")},
        "checks": {k: dict(v, secs_mean=round(v["secs"] / v["runs"], 1) if v["runs"] else 0)
                   for k, v in per_check.items()},
        "rule_hits": dict(rule_hits),
        "candidates": {
            "checks_never_failed_in_10_plus_runs": never_failed,
            "checks_never_run": never_ran,
            "rules_never_hit": rules_never,
        },
    }


def show(s):
    print("Stops checked: %d   changes: %d   first-pass rate: %s   unverified: %d"
          % (s["stops"], s["changes"],
             "-" if s["first_pass_rate"] is None else "%d%%" % (s["first_pass_rate"] * 100),
             s["unverified"]))
    print("Gate time per stop: mean %ss, max %ss" % (s["gate_secs_mean"], s["gate_secs_max"]))
    print("Results: " + ", ".join("%s %d" % kv for kv in sorted(s["results"].items())))
    print("Final verification: %d runs, %d failed   verifier: %d accept, %d reject"
          % (s["verify_runs"], s["verify_failed"], s["verdicts"]["ACCEPT"],
             s["verdicts"]["REJECT"]))
    if s["checks"]:
        print("\nChecks (runs, caught, pre-existing, skipped, mean time):")
        for cmd, c in sorted(s["checks"].items(), key=lambda kv: -kv[1]["secs"]):
            print("  %-48s %4d %4d %4d %4d %7.1fs" % (cmd[:48], c["runs"], c["failed"],
                                                     c["preexisting"], c["skipped"],
                                                     c["secs_mean"]))
    if s["rule_hits"]:
        print("\nRules that fired:")
        for r, n in sorted(s["rule_hits"].items(), key=lambda kv: -kv[1]):
            print("  %4d  %s" % (n, r))
    cand = s["candidates"]
    if any(cand.values()):
        print("\nCandidates to remove or retune (each still has to earn its place):")
        for c in cand["checks_never_failed_in_10_plus_runs"]:
            print("  never caught anything in 10+ runs: %s" % c)
        for c in cand["checks_never_run"]:
            print("  never ran (its `when` may be wrong): %s" % c)
        for r in cand["rules_never_hit"]:
            print("  rule never fired: %s" % r)


def main():
    if "--verdict" in sys.argv:
        v = sys.argv[sys.argv.index("--verdict") + 1].upper()
        if v not in ("ACCEPT", "REJECT"):
            print("--verdict takes ACCEPT or REJECT")
            return 1
        log({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "verdict", "verdict": v})
        return 0
    days = None
    if "--days" in sys.argv:
        days = float(sys.argv[sys.argv.index("--days") + 1])
    s = summarise(entries(days), load_config())
    if "--json" in sys.argv:
        print(json.dumps(s, indent=2))
    else:
        show(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
