#!/usr/bin/env python3
"""Check the direct tree difference, including force pushes with diverged history."""
import os
import subprocess
import sys


def main():
    refs = [
        subprocess.check_output(
            ["git", "rev-parse", "--verify", "--end-of-options", os.environ[key] + "^{commit}"],
            text=True,
        ).strip()
        for key in ("PRE_COMMIT_FROM_REF", "PRE_COMMIT_TO_REF")
    ]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if refs[1] != head:
        raise ValueError("Quality checks must run in the candidate checkout.")
    # Yarn rewrites this tracked cache during immutable installation.
    subprocess.run([
        "git", "diff", "--quiet", "HEAD", "--", ".", ":(exclude).yarn/install-state.gz",
    ], check=True)
    changed = subprocess.check_output([
        "git", "diff", "--name-only", "--diff-filter=ACMRT", "-z", *refs, "--",
    ])
    files = ["./" + os.fsdecode(path) for path in changed.split(b"\0") if path]
    # pre-commit --from-ref uses merge-base semantics, which differ on force pushes.
    return subprocess.call([
        sys.executable, "bin/pre-commit.py", "run", "--hook-stage", "manual", "--files", *files,
    ])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"Cannot check CI candidate: {error}")
