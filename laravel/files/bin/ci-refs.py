#!/usr/bin/env python3
"""Resolve explicit comparison commits. Missing history must fail, not skip checks."""
import json
import os
from pathlib import Path
import subprocess
import sys


def commit(ref):
    if not isinstance(ref, str) or not ref or set(ref) == {"0"}:
        raise ValueError("Missing or zero base/head. Supply an existing base_ref in a manual run.")
    return subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"],
        text=True,
    ).strip()


def main():
    event = os.environ["GITHUB_EVENT_NAME"]
    payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    head = commit("HEAD")
    if head != commit(os.environ["GITHUB_SHA"]):
        raise ValueError("Checkout does not match the workflow candidate.")
    scan_head = head
    if event == "pull_request":
        base = commit(payload["pull_request"]["base"]["sha"])
        scan_head = commit(payload["pull_request"]["head"]["sha"])
        for parent in (base, scan_head):
            subprocess.run(["git", "merge-base", "--is-ancestor", parent, head], check=True)
    elif event == "push":
        base = commit(payload["before"])
    elif event == "workflow_dispatch":
        base = commit(payload["inputs"]["base_ref"])
    else:
        raise ValueError(f"Unsupported comparison event: {event}")
    print(f"from_ref={base}\nto_ref={head}\nscan_to_ref={scan_head}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"Cannot select CI comparison: {error}")
