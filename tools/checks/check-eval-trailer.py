#!/usr/bin/env python3
"""Does every change to a file the gate cases read say how the gates scored it?

The gate cases read a set of harness files (tools/evals/workflow/watched.txt).
A change to one of them can change what the stages do. Each non-merge commit in
the range that touches one of those files needs an `Eval:` trailer, the last
line of `eval.py gates`, or a reason for not running it:

    Eval: gates 51/60 PASS -> 55/60 PASS, flaky 6 -> 2 (BETTER); <run>
    Eval: not run - wording only, no decision changed

A bare "not run", or no trailer, fails. The `Review-eval:` trailer is another
check's (check-rescore.py) and counts for nothing here. Only commits from the
one that adds this script on are checked. Git reads trailers from the last
paragraph of the message only, so the `Eval:` line goes there.

Usage:
    check-eval-trailer.py --range origin/main..HEAD
    check-eval-trailer.py --range "$BEFORE..$AFTER"

Exit: 0 clean · 1 a watched change without a result · 2 git or file error.
"""
import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = 'tools/checks/check-eval-trailer.py'
WATCHED_FILE = Path(__file__).resolve().parents[1] / 'evals' / 'workflow' / 'watched.txt'
NOT_RUN = re.compile(r'^not run\s*[-—:]\s*\S', re.I)


def git(*args):
    out = subprocess.run(['git', *args], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(2)
    return out.stdout


def read_watched(path):
    lines = (line.strip() for line in Path(path).read_text().splitlines())
    return [line for line in lines if line and not line.startswith('#')]


def start_commit():
    """The commit that added this script, or None when history has none."""
    added = git('log', '--reverse', '--diff-filter=A', '--format=%H', '--', SCRIPT_PATH).split()
    return added[0] if added else None


def has_result(sha):
    values = git('log', '-1', '--format=%(trailers:key=Eval,valueonly,unfold)', sha).split('\n')
    return any(v.strip() and (not v.strip().lower().startswith('not run') or NOT_RUN.match(v.strip()))
               for v in values)


def missing(rng, watched, start):
    """[(short sha, subject, watched files)] for watched changes without a result."""
    commits = git('rev-list', '--no-merges', rng).split()
    if start is None:
        return []
    older = set(git('rev-list', '--no-merges', start).split()) - {start}
    bad = []
    for sha in commits:
        if sha in older:
            continue
        files = git('diff-tree', '--no-commit-id', '--name-only', '-r', sha).split()
        hit = [f for f in files if any(fnmatch.fnmatch(f, g) for g in watched)]
        if not hit or has_result(sha):
            continue
        bad.append((sha[:7], git('log', '-1', '--format=%s', sha).strip(), hit))
    return bad


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--range', required=True)
    parser.add_argument('--watched', default=str(WATCHED_FILE))
    args = parser.parse_args(argv)
    if re.match(r'^0+\.\.', args.range):
        print('Eval trailer: new branch, no range to check.')
        return 0
    try:
        watched = read_watched(args.watched)
    except OSError as err:
        print(f'check-eval-trailer: cannot read {args.watched}: {err}', file=sys.stderr)
        return 2
    try:
        bad = missing(args.range, watched, start_commit())
    except SystemExit:
        print(f'check-eval-trailer: cannot read {args.range}', file=sys.stderr)
        return 2
    if not bad:
        print('Eval trailer: every change to a watched file carries an Eval result.')
        return 0
    print('Eval trailer: changes to watched files without an Eval trailer (REQ-017):')
    for sha, subject, files in bad:
        print(f'  {sha} {subject}\n      {", ".join(files)}')
    print('Run `eval.py gates` and put its last line in the commit, or state why not:\n'
          '  Eval: not run - <reason>')
    return 1


if __name__ == '__main__':
    sys.exit(main())
