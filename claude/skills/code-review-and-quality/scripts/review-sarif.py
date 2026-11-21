#!/usr/bin/env python3
"""One review SARIF file per ticket: docs/reviews/<TICKET>.sarif (ADR 0145).

Each /review round appends its runs. Every run carries properties.round,
properties.approach, properties.reviewedCommit and properties.closing.

    review-sarif.py round TICKET [--new-approach]     # the next round, and how many count
    review-sarif.py add TICKET ROUND.sarif --commit SHA [--closing] [--new-approach]
    review-sarif.py latest TICKET [--open] [--round N | --all]   # findings, one line each
    review-sarif.py resolve TICKET ID=RESOLUTION... [--round N]
    review-sarif.py merge TICKET                      # fold old <TICKET>-<sha>.sarif files in

A round counts toward the round-4 stop when it is not a closing round and
belongs to the current approach. The current approach is the highest one in
the file. Old per-round files must be merged first; every command except
merge refuses to run while they exist.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RESOLUTIONS = ('open', 'fixed', 'refuted', 'answered', 'accepted', 'deferred', 'follow-up', 'declined')


def review_dir():
    out = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit('review-sarif: not in a git repository; pass --dir')
    return Path(out.stdout.strip()) / 'docs' / 'reviews'


def old_files(directory, ticket):
    pattern = re.compile(rf'^{re.escape(ticket)}-[0-9a-f]{{7,40}}\.sarif$')
    return sorted(p for p in directory.glob(f'{ticket}-*.sarif') if pattern.match(p.name))


def refuse_old(directory, ticket):
    old = old_files(directory, ticket)
    if old:
        raise SystemExit(f'review-sarif: {len(old)} old per-round file(s) for {ticket} '
                         f'({old[0].name} ...). Run: review-sarif.py merge {ticket}')


def load(path):
    if not path.exists():
        return {'version': '2.1.0', '$schema': 'https://json.schemastore.org/sarif-2.1.0.json', 'runs': []}
    return json.loads(path.read_text())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def rounds(data):
    """[(approach, round, closing, commit)] in file order, one per round."""
    seen = []
    for run in data.get('runs', []):
        p = run.get('properties', {})
        key = (p.get('approach', 1), p.get('round', 0), bool(p.get('closing')), p.get('reviewedCommit', ''))
        if key not in seen:
            seen.append(key)
    return seen


def next_round(data, new_approach=False):
    """(approach, round label, rounds that count toward the stop including this one)."""
    rs = rounds(data)
    approach = max((a for a, *_ in rs), default=1)
    if new_approach and rs:
        return approach + 1, 1, 1
    mine = [r for a, r, _, _ in rs if a == approach]
    counted = len({r for a, r, closing, _ in rs if a == approach and not closing})
    return approach, max(mine, default=0) + 1, counted + 1


def tag(run, ticket, approach, rnd, commit, closing):
    props = run.setdefault('properties', {})
    props.update(round=rnd, approach=approach, reviewedCommit=commit, closing=closing)
    driver = run.get('tool', {}).get('driver', {}).get('name', 'reviewer')
    run['automationDetails'] = {'id': f'review/{ticket}/a{approach}r{rnd}/{driver}'}
    return run


def cmd_round(args, directory):
    refuse_old(directory, args.ticket)
    approach, rnd, counted = next_round(load(directory / f'{args.ticket}.sarif'), args.new_approach)
    print(f'approach={approach} round={rnd} counted={counted}')
    return 0


def cmd_add(args, directory):
    refuse_old(directory, args.ticket)
    path = directory / f'{args.ticket}.sarif'
    data = load(path)
    approach, rnd, counted = next_round(data, args.new_approach)
    new = json.loads(Path(args.file).read_text()).get('runs', [])
    if not new:
        raise SystemExit(f'review-sarif: {args.file} has no runs')
    data['runs'].extend(tag(r, args.ticket, approach, rnd, args.commit, args.closing) for r in new)
    save(path, data)
    print(f'{path}: approach={approach} round={rnd} counted={counted - args.closing}'
          f'{" closing" if args.closing else ""} runs={len(new)}')
    return 0


def newest(data):
    rs = rounds(data)
    if not rs:
        raise SystemExit('review-sarif: no review rounds recorded')
    return rs[-1]


def in_round(run, key):
    p = run.get('properties', {})
    return (p.get('approach', 1), p.get('round', 0), bool(p.get('closing')), p.get('reviewedCommit', '')) == key


def cmd_latest(args, directory):
    refuse_old(directory, args.ticket)
    data = load(directory / f'{args.ticket}.sarif')
    key = newest(data)
    if args.round is not None:
        keys = [k for k in rounds(data) if k[1] == args.round and k[0] == key[0]]
        if not keys:
            raise SystemExit(f'review-sarif: no round {args.round} in approach {key[0]}')
    else:
        keys = rounds(data) if args.all else [key]
    for k in keys:
        approach, rnd, closing, commit = k
        print(f'approach={approach} round={rnd} closing={str(closing).lower()} reviewedCommit={commit}')
        print_findings(data, k, args.open)
    return 0


def print_findings(data, key, only_open):
    for run in data['runs']:
        if not in_round(run, key):
            continue
        for r in run.get('results', []):
            p = r.get('properties', {})
            res = p.get('resolution', 'open')
            if only_open and res != 'open':
                continue
            loc = r.get('locations', [{}])[0].get('physicalLocation', {})
            where = loc.get('artifactLocation', {}).get('uri', '')
            if loc.get('region', {}).get('startLine'):
                where += f":{loc['region']['startLine']}"
            pre = ' pre-existing' if r.get('baselineState') == 'unchanged' else ''
            text = r.get('message', {}).get('text', '').replace('\n', ' ')
            print(f"{r.get('ruleId')} | {p.get('disposition', '?')}{pre} | {res} | {where} | {text}")


def cmd_resolve(args, directory):
    refuse_old(directory, args.ticket)
    path = directory / f'{args.ticket}.sarif'
    data = load(path)
    for pair in args.pairs:
        rid, _, res = pair.partition('=')
        if res not in RESOLUTIONS:
            raise SystemExit(f'review-sarif: {pair}: resolution must be one of {", ".join(RESOLUTIONS)}')
        hits = [(run, r) for run in data['runs'] for r in run.get('results', []) if r.get('ruleId') == rid
                and (args.round is None or run.get('properties', {}).get('round') == args.round)]
        if not hits:
            raise SystemExit(f'review-sarif: {rid} not found' + (f' in round {args.round}' if args.round else ''))
        last = max(hits, key=lambda h: data['runs'].index(h[0]))[0]
        key = next(k for k in rounds(data) if in_round(last, k))
        for run, r in hits:
            if in_round(run, key):
                r.setdefault('properties', {})['resolution'] = res
        print(f'{rid}: {res} (approach {key[0]}, round {key[1]})')
    save(path, data)
    return 0


def reviewed_at(path):
    """When the reviewed commit in the name was made; else when the file was added; else its mtime.
    The add commit alone is not enough: one commit moved many old files at once."""
    sha = re.search(r'-([0-9a-f]{7,40})\.sarif$', path.name).group(1)
    for cmd in (['git', 'show', '-s', '--format=%ct', sha],
                ['git', 'log', '--diff-filter=A', '--format=%ct', '-1', '--', path.name]):
        out = subprocess.run(cmd, capture_output=True, text=True, cwd=path.parent)
        if out.returncode == 0 and out.stdout.strip():
            return int(out.stdout.split()[0])
    return int(path.stat().st_mtime)


def cmd_merge(args, directory):
    old = sorted(old_files(directory, args.ticket), key=reviewed_at)
    if not old:
        print(f'review-sarif: no old files for {args.ticket}')
        return 0
    path = directory / f'{args.ticket}.sarif'
    data = load(path)
    done = rounds(data)
    base = max((r for a, r, _, _ in done if a == 1), default=0)
    for i, f in enumerate(old, start=base + 1):
        commit = re.search(r'-([0-9a-f]{7,40})\.sarif$', f.name).group(1)
        for run in json.loads(f.read_text()).get('runs', []):
            data['runs'].append(tag(run, args.ticket, 1, i, commit, False))
    save(path, data)
    in_git = subprocess.run(['git', 'rev-parse'], cwd=directory, capture_output=True).returncode == 0
    if in_git:
        subprocess.run(['git', 'add', path.name], cwd=directory, check=True)
    for f in old:
        tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', f.name], cwd=directory,
                                 capture_output=True).returncode == 0
        if tracked:
            subprocess.run(['git', 'rm', '-q', f.name], cwd=directory, check=True)
        else:
            f.unlink()
    print(f'{path}: merged {len(old)} file(s) as rounds {base + 1}-{base + len(old)}')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--dir', type=Path)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('round'); p.add_argument('ticket'); p.add_argument('--new-approach', action='store_true')
    p = sub.add_parser('add'); p.add_argument('ticket'); p.add_argument('file')
    p.add_argument('--commit', required=True); p.add_argument('--closing', action='store_true')
    p.add_argument('--new-approach', action='store_true')
    p = sub.add_parser('latest'); p.add_argument('ticket'); p.add_argument('--open', action='store_true')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--round', type=int); group.add_argument('--all', action='store_true')
    p = sub.add_parser('resolve'); p.add_argument('ticket'); p.add_argument('pairs', nargs='+')
    p.add_argument('--round', type=int)
    p = sub.add_parser('merge'); p.add_argument('ticket')
    args = parser.parse_args(argv)
    directory = args.dir or review_dir()
    return {'round': cmd_round, 'add': cmd_add, 'latest': cmd_latest,
            'resolve': cmd_resolve, 'merge': cmd_merge}[args.cmd](args, directory)


if __name__ == '__main__':
    sys.exit(main())
