#!/usr/bin/env python3
"""The eval steps you skipped, from a project checkout. No model, no network.

    eval.py todo [--count] [--repo <project>] [--log <observation log>]

Lists
  - each ticket with an Approved `docs/tasks/<TICKET>-plan.md`, a `(<TICKET> T` commit subject on the
    default branch and no row in the "Plan recall" table of the harness observation log, with the
    `eval.py recall` command that scores it;
  - each "Shipped bugs" row whose "Eval case" column is empty or `—`, with the `eval.py bugs add`
    command that builds the case.

Without `docs/tasks/` only the bug rows are listed. `--count` prints `<tickets> <bugs>` and nothing
else. The exit code is 0 whatever it finds, so a hook can call it.
"""
import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE.parents[1] / 'docs' / 'observation-log.md'
EVAL = HERE / 'eval.py'
SHA = re.compile(r'\b[0-9a-f]{7,40}\b')
NO_CASE = ('', '—')


def log_table(text, heading):
    """The rows of the first table under `## <heading>` in the observation log, each as
    `{lower-case column name: cell text}`; None when the heading or its table is missing. Prose,
    the `|---|` rule and other sections do not count. A row shorter than the header lacks the
    keys of its missing cells."""
    section = re.search(rf'^## {re.escape(heading)}\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    header, rows = None, []
    for line in section.group(1).splitlines() if section else []:
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if header is None:
            header = [c.lower() for c in cells]
        elif not all(re.fullmatch(r':?-+:?', c) for c in cells):
            rows.append(dict(zip(header, cells)))
    return None if header is None else rows


def git(repo, *args):
    """git's stdout, or None when it fails (not a repository, no such branch)."""
    done = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else None


def default_branch(repo):
    """The default branch's name as origin reports it, else `main` or `master`; None when none exists."""
    named = (git(repo, 'symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD') or '').strip()
    for name in [named.removeprefix('origin/'), 'main', 'master']:
        if name and git(repo, 'rev-parse', '--verify', '--quiet', name) is not None:
            return name
    return None


def approved_plans(repo):
    """The tickets whose `docs/tasks/<TICKET>-plan.md` has the status Approved."""
    tickets = []
    for plan in sorted((repo / 'docs' / 'tasks').glob('*-plan.md')):
        if re.search(r'^Status:\s*Approved\b', plan.read_text(), re.M):
            tickets.append(plan.name.removesuffix('-plan.md'))
    return tickets


def shipped_range(repo, default, subjects, ticket):
    """The `--range` that holds the ticket's `(<ticket> T` commits on `default`, or None when none is there."""
    mark = re.compile(rf'\({re.escape(ticket)} T')
    first = next((sha for sha, subject in subjects if mark.search(subject)), None)
    if first is None:
        return None
    return f'{first[:12]}^..{default}' if git(repo, 'rev-parse', '--verify', '--quiet', f'{first}^') is not None else default


def recall_command(repo, ticket, rev_range):
    plans = [f'docs/tasks/{ticket}-plan.md']
    if (repo / 'docs' / 'tasks' / f'{ticket}-todo.md').is_file():
        plans.append(f'docs/tasks/{ticket}-todo.md')
    flags = ' '.join(f'--plan {p}' for p in plans)
    return f'python3 {shlex.quote(str(EVAL))} recall --repo {shlex.quote(str(repo))} {flags} --range {rev_range} --ticket {ticket} --subject-only'


def bug_command(repo, sha):
    return f'python3 {shlex.quote(str(EVAL))} bugs add --repo {shlex.quote(str(repo))} --from-log {sha} --defect <term>'


def collect(repo, log):
    """`{'tickets': [{'ticket', 'command'}], 'bugs': [{'bug', 'sha', 'command'}]}`.
    Raises ValueError when the log cannot be read or lacks a table the list needs."""
    repo = Path(repo).resolve()
    try:
        text = Path(log).read_text()
    except OSError as err:
        raise ValueError(f'cannot read the observation log: {err}')
    bug_rows = log_table(text, 'Shipped bugs')
    if bug_rows is None:
        raise ValueError('the observation log has no "Shipped bugs" table')
    bugs = []
    for row in bug_rows:
        if row.get('eval case', '') not in NO_CASE:
            continue
        sha = next(iter(SHA.findall(row.get('fix commit', ''))), None)
        bugs.append({'bug': row.get('bug', ''), 'sha': sha, 'command': bug_command(repo, sha) if sha else None})

    tickets = []
    default = default_branch(repo) if (repo / 'docs' / 'tasks').is_dir() else None
    plans = approved_plans(repo) if default else []
    if plans:
        recall_rows = log_table(text, 'Plan recall')
        if recall_rows is None:
            raise ValueError('the observation log has no "Plan recall" table')
        scored = ' '.join(row.get('ticket', '') for row in recall_rows)
        out = git(repo, 'log', '--no-merges', '--reverse', '--format=%H%x1f%s', default) or ''
        subjects = [line.split('\x1f', 1) for line in out.splitlines() if '\x1f' in line]
        for ticket in plans:
            if re.search(rf'(?<!\w){re.escape(ticket)}(?!\w)', scored):
                continue
            rev_range = shipped_range(repo, default, subjects, ticket)
            if rev_range:
                tickets.append({'ticket': ticket, 'command': recall_command(repo, ticket, rev_range)})
    return {'tickets': tickets, 'bugs': bugs}


def render(found):
    if not found['tickets'] and not found['bugs']:
        return 'nothing to catch up'
    lines = []
    if found['tickets']:
        lines.append(f'Shipped tickets without a Plan recall row ({len(found["tickets"])}):')
        for item in found['tickets']:
            lines += [f'  {item["ticket"]}', f'    {item["command"]}']
    if found['bugs']:
        lines.append(f'Shipped bugs without an eval case ({len(found["bugs"])}):')
        for item in found['bugs']:
            lines += [f'  {item["bug"][:100]}', f'    {item["command"] or "no fix commit in the row; add one"}']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='eval.py todo', description=__doc__.split('\n')[0])
    parser.add_argument('--count', action='store_true', help='print "<tickets> <bugs>" only')
    parser.add_argument('--repo', type=Path, default=Path('.'), help='the project checkout (default: here)')
    parser.add_argument('--log', type=Path, default=LOG, help='the observation log (default: the harness docs/observation-log.md)')
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        found = collect(args.repo, args.log)
    except ValueError as why:
        print(why, file=sys.stderr)
        if not args.count:
            return 0
        found = {'tickets': [], 'bugs': []}
    print(f'{len(found["tickets"])} {len(found["bugs"])}' if args.count else render(found))
    return 0


if __name__ == '__main__':
    sys.exit(main())
