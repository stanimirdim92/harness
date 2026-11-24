#!/usr/bin/env python3
"""Apply the same size ratchet to Git's index and CI revision pairs."""
import argparse
import fnmatch
import os
import subprocess
import sys

MAX_BYTES = 30_000

EXCLUDED = (
    "*.lock", "package-lock.json", "*/package-lock.json", "pnpm-lock.yaml",
    "_ide_helper.php", ".phpstorm.meta.php", "phpstan-baseline.neon",
    "deptrac.baseline.yaml", "database/schema/*", "docs/*", "AGENTS.md",
    "public/*", ".yarn/*", ".claude/*", "vendor/*", "node_modules/*", "resources/views/vendor/*",
    "*.min.js", "*.min.css", "*.map", "*.png", "*.jpg", "*.jpeg", "*.gif",
    "*.webp", "*.ico", "*.svg", "*.pdf", "*.ttf", "*.otf", "*.woff", "*.woff2",
    "*.zip", "*.gz",
)


def git(*arguments):
    return subprocess.check_output(["git", *arguments])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-ref", default=os.environ.get("PRE_COMMIT_FROM_REF"))
    parser.add_argument("--to-ref", default=os.environ.get("PRE_COMMIT_TO_REF"))
    args = parser.parse_args()
    if bool(args.from_ref) != bool(args.to_ref):
        parser.error("--from-ref and --to-ref must be supplied together")
    if args.from_ref:
        base, head = [
            git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
            for ref in (args.from_ref, args.to_ref)
        ]
        comparison = [base, head]
    else:
        head = ""
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "HEAD"], capture_output=True
        )
        if result.returncode not in (0, 1):
            raise RuntimeError("Cannot resolve the staged comparison base.")
        base = result.stdout.decode().strip() if result.returncode == 0 else None
        comparison = ["--cached"]
    fields = iter(git(
        "diff", *comparison, "--name-status", "--diff-filter=ACMR",
        "-M", "-C", "--find-copies-harder", "-z", "--",
    ).split(b"\0")[:-1])
    failures = []
    for raw_status in fields:
        status = raw_status.decode("ascii")
        previous = os.fsdecode(next(fields))
        path = os.fsdecode(next(fields)) if status[0] in "RC" else previous
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in EXCLUDED):
            continue
        size = int(git("cat-file", "-s", f"{head}:{path}"))
        if size <= MAX_BYTES:
            continue
        if base and status[0] in "MR":
            old_size = int(git("cat-file", "-s", f"{base}:{previous}"))
            if size <= old_size:
                continue
        failures.append(f"{path!r}: {size} bytes exceeds {MAX_BYTES} bytes (30 KB); new or growing oversized file")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        print("Split files by responsibility. Existing oversized files may shrink but cannot grow.", file=sys.stderr)
    return bool(failures)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, StopIteration, ValueError) as error:
        print(f"File size check failed: {error}", file=sys.stderr)
        sys.exit(1)
