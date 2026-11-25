#!/usr/bin/env python3
"""One entry point for the evals.

    eval.py                                  print the suites
    eval.py gates|tasks|bugs [--case ID] [--tag TAG] [--split S] [--trials N] [--jobs N]
    eval.py recall <recall.py flags>         plan-recall, flags passed on unchanged
    eval.py baseline <suite> [<run>]         make a run the suite's baseline
    eval.py report [<suite>]                 print the last run's report again
    eval.py review <run> <case> ok|bad "<note>"

A suite registers in SUITES with its question, when to run it, and `build`,
a function that returns the suite. A suite whose `build` is None is not built
yet: naming it prints that and exits 2. A built suite has the interface in
`core.py` and one more method, `all_cases()`, which lists every case as
`{'id', 'split', 'tags'}`. The core never lists the cases itself. A built
`recall` suite has `run(argv) -> int` instead: `argv` is everything after
`recall`, and the return value is the exit code.

`--case` and `--tag` repeat. A case is selected when its id is any `--case`
or it carries any `--tag`; with neither flag every case is selected.
`--split` then keeps the cases of that split.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import core

HERE = Path(__file__).resolve().parent
README = HERE / 'README.md'


def build_gates():
    sys.path.append(str(HERE / 'workflow'))
    from run import GatesSuite
    return GatesSuite()


class RecallSuite:
    """plan-recall's `recall.py`, run as it is. It reads git and the plan: no model, no trials."""

    def run(self, argv):
        return subprocess.run([sys.executable, str(HERE / 'plan-recall' / 'recall.py'), *argv]).returncode


def build_recall():
    return RecallSuite()


SUITES = {
    'gates': {'question': 'Does the pipeline make the right calls on small made-up cases?',
              'when': 'after you change a command, agent, skill or reference',
              'cost': None, 'build': build_gates, 'jobs': 4},
    'tasks': {'question': 'Does the pipeline build a working feature from a ticket?',
              'when': 'after you change how build, review or test behave',
              'cost': None, 'build': None},
    'bugs': {'question': 'Does /review catch bugs that really shipped?',
             'when': 'after you change /review or a reviewer',
             'cost': None, 'build': None},
    'recall': {'question': 'Did the plan name the files that really changed?',
               'when': 'after a ticket ships',
               'cost': 'free', 'build': build_recall},
}
RUNNABLE = ('gates', 'tasks', 'bugs')


def measured_costs(readme_text):
    """The last measured cost of each suite, read from the README "Measured" section.
    That section measures the `workflow/` cases, which are the gates."""
    section = re.search(r'^## Measured\n(.*?)(?=^## |\Z)', readme_text, re.M | re.S)
    if not section or '`workflow/`' not in section.group(1):
        return {}
    cost = re.search(r'^\|\s*Total cost\s*\|\s*\$([\d.]+)\s*\|', section.group(1), re.M)
    cases = re.search(r'^\|\s*Cases\s*\|\s*([^|]+?)\s*\|', section.group(1), re.M)
    if not cost:
        return {}
    return {'gates': f'${float(cost.group(1)):.2f}' + (f' ({re.sub(r"^(\d+)", r"\1 cases", cases.group(1))})' if cases else '')}


def suite_table(suites, readme_text):
    measured = measured_costs(readme_text)
    lines = []
    for name, entry in suites.items():
        cost = entry.get('cost') or measured.get(name, 'unmeasured')
        lines += [name, f'  question: {entry["question"]}', f'  run when: {entry["when"]}',
                  f'  last measured cost: {cost}', '']
    return '\n'.join(lines).rstrip()


def select(cases, ids, tags, split):
    """The cases the flags select. Raises ValueError for an unknown `--case`."""
    unknown = sorted(set(ids) - {c['id'] for c in cases})
    if unknown:
        raise ValueError(f'unknown case: {", ".join(unknown)}')
    picked = [c for c in cases if (c['id'] in ids or set(c.get('tags', [])) & set(tags)) or not (ids or tags)]
    return [c for c in picked if not split or c.get('split') == split]


def positive(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError('must be 1 or more')
    return value


def parser_for(suites):
    parser = argparse.ArgumentParser(prog='eval.py', description=__doc__.split('\n')[0])
    commands = parser.add_subparsers(dest='command')
    for name in RUNNABLE:
        sub = commands.add_parser(name, help=suites[name]['question'])
        sub.add_argument('--case', action='append', default=[], help='run this case (repeatable)')
        sub.add_argument('--tag', action='append', default=[], help='run the cases with this tag (repeatable)')
        sub.add_argument('--split', choices=('optimization', 'holdout'), help='keep only this split')
        sub.add_argument('--trials', type=positive, default=core.DEFAULT_TRIALS,
                         help=f'trials per case (default {core.DEFAULT_TRIALS})')
        jobs = suites[name].get('jobs', 1)
        sub.add_argument('--jobs', type=positive, default=jobs, help=f'trials to run at the same time (default {jobs})')
    commands.add_parser('recall', help=suites['recall']['question'])
    sub = commands.add_parser('baseline', help='make a run the suite baseline')
    sub.add_argument('suite', choices=list(suites))
    sub.add_argument('run', nargs='?', help='run folder name (default: the latest run)')
    sub = commands.add_parser('report', help="print the last run's report again")
    sub.add_argument('suite', nargs='?', choices=list(suites))
    sub = commands.add_parser('review', help='record a semantic review of one case')
    sub.add_argument('run')
    sub.add_argument('case')
    sub.add_argument('verdict', choices=('ok', 'bad'))
    sub.add_argument('note')
    return parser


def build(suites, name):
    """The built suite, or None after printing that it is not built yet."""
    factory = suites[name]['build']
    if factory is None:
        print(f'{name}: not built yet', file=sys.stderr)
        return None
    return factory()


def main(argv=None, suites=None, root=core.ROOT, readme=README):
    suites = SUITES if suites is None else suites
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ['recall']:  # argparse cannot pass on a leading flag such as `--repo`
        suite = build(suites, 'recall')
        return 2 if suite is None else suite.run(argv[1:])
    parser = parser_for(suites)
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return stop.code or 0
    if args.command is None:
        print(suite_table(suites, Path(readme).read_text() if Path(readme).is_file() else ''))
        return 0
    if args.command == 'report':
        return core.report(root=root, suite=args.suite)
    if args.command == 'review':
        return core.review(args.run, args.case, args.verdict, args.note, root=root)
    suite = build(suites, args.command if args.command != 'baseline' else args.suite)
    if suite is None:
        return 2
    if args.command == 'baseline':
        return core.baseline(args.suite, [c['id'] for c in suite.all_cases()], run=args.run, root=root)
    try:
        cases = select(suite.all_cases(), args.case, args.tag, args.split)
    except ValueError as why:
        print(why, file=sys.stderr)
        return 2
    if not cases:
        print('no case matches those flags', file=sys.stderr)
        return 2
    return core.run(suite, cases, trials=args.trials, jobs=args.jobs, root=root)


if __name__ == '__main__':
    sys.exit(main())
