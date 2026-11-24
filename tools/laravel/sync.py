#!/usr/bin/env python3
"""Mirror the Leadbuster quality setup into laravel/files/.

  sync.py check   exit 1 when laravel/files/ differs from Leadbuster main,
                  or a watched Leadbuster file is in no include or skip line
  sync.py apply   copy from Leadbuster main and record the commit in SOURCE.lock

Copies come from the committed --ref (default main), never from the working
tree or a ticket branch. The source is --source, else $LEADBUSTER_DIR, else
/var/www/html/leadbuster.

Exit codes: 0 in sync, 1 drift, 2 MANIFEST error, 3 no Leadbuster checkout.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[2]


class ManifestError(Exception):
    pass


def to_regex(pattern):
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith('**', i):
            out.append('.*')
            i += 2
        elif pattern[i] == '*':
            out.append('[^/]*')
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile(''.join(out) + r'\Z')


def read_manifest(path):
    includes, skips, watches = [], [], []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        words = line.split()
        if not words or words[0].startswith('#'):
            continue
        kind = words[0]
        if kind == 'include' and len(words) == 3:
            includes.append((words[1], words[2], to_regex(words[2])))
        elif kind == 'skip' and len(words) >= 3:
            skips.append(to_regex(words[1]))
        elif kind == 'watch' and len(words) == 2:
            watches.append(to_regex(words[1]))
        else:
            raise ManifestError(f'{path}:{number}: cannot read "{line.strip()}"')
    return includes, skips, watches


def git(source, *args, text=True):
    return subprocess.run(['git', '-C', str(source), *args], check=True,
                          capture_output=True, text=text).stdout


def source_tree(source, ref):
    """Map each committed path at ref to (mode, blob sha)."""
    tree = {}
    for line in git(source, 'ls-tree', '-r', '-z', ref).split('\0'):
        if not line:
            continue
        meta, path = line.split('\t', 1)
        mode, kind, sha = meta.split()
        if kind == 'blob':
            tree[path] = (mode, sha)
    return tree


def plan(source, laravel, ref):
    includes, skips, watches = read_manifest(laravel / 'MANIFEST')
    tree = source_tree(source, ref)
    wanted, groups = {}, {}
    for group, pattern, regex in includes:
        hits = [p for p in tree if regex.match(p)]
        if not hits:
            raise ManifestError(f'include matches nothing at {ref}: {pattern}')
        for path in hits:
            wanted[path] = tree[path]
            groups[path] = group
    unlisted = sorted(p for p in tree if p not in wanted
                      and any(w.match(p) for w in watches)
                      and not any(s.match(p) for s in skips))
    return wanted, groups, unlisted


def blob(source, sha):
    return subprocess.run(['git', '-C', str(source), 'cat-file', 'blob', sha],
                          check=True, capture_output=True).stdout


def local_state(path):
    """(kind, content, executable) of a copy, or None when it is missing."""
    if path.is_symlink():
        return ('link', os.readlink(path).encode(), False)
    if path.is_file():
        return ('file', path.read_bytes(), os.access(path, os.X_OK))
    return None


def wanted_state(source, mode, sha):
    if mode == '120000':
        return ('link', blob(source, sha), False)
    return ('file', blob(source, sha), mode == '100755')


def local_copies(files):
    if not files.exists():
        return set()
    return {str(p.relative_to(files)) for p in files.rglob('*')
            if p.is_symlink() or p.is_file()}


def diff(source, laravel, wanted):
    files = laravel / 'files'
    changes = []
    for path, (mode, sha) in sorted(wanted.items()):
        have = local_state(files / path)
        if have is None:
            changes.append(('added', path))
        elif have != wanted_state(source, mode, sha):
            changes.append(('changed', path))
    for path in sorted(local_copies(files) - set(wanted)):
        changes.append(('removed', path))
    return changes


def uncommitted(source, wanted, ref):
    if git(source, 'rev-parse', '--abbrev-ref', 'HEAD').strip() != ref:
        return []
    status = git(source, 'status', '--porcelain', '-z', '--untracked-files=no')
    paths = [entry[3:] for entry in status.split('\0') if len(entry) > 3]
    return sorted(p for p in paths if p in wanted)


def report(changes, unlisted, dirty):
    for kind, path in changes:
        print(f'{kind:<8} {path}')
    for path in unlisted:
        print(f'unlisted {path}  (add an include or a skip line to laravel/MANIFEST)')
    for path in dirty:
        print(f'note: uncommitted in Leadbuster, not synced: {path}')


def write_copy(source, target, mode, sha):
    if target.is_symlink() or target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == '120000':
        os.symlink(blob(source, sha).decode(), target)
        return
    target.write_bytes(blob(source, sha))
    target.chmod(0o755 if mode == '100755' else 0o644)


def prune_empty_dirs(files):
    for folder in sorted((p for p in files.rglob('*') if p.is_dir() and not p.is_symlink()),
                         key=lambda p: len(p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()


def apply(source, laravel, wanted, groups, changes, ref):
    files = laravel / 'files'
    for kind, path in changes:
        if kind == 'removed':
            (files / path).unlink()
        else:
            write_copy(source, files / path, *wanted[path])
    if files.exists():
        prune_empty_dirs(files)
    head = git(source, 'rev-parse', ref).strip()
    date = git(source, 'show', '-s', '--format=%cI', ref).strip()
    (laravel / 'SOURCE.lock').write_text(
        f'commit {head}\ncommitted {date}\n'
        f'synced {datetime.date.today().isoformat()}\n')
    touched = sorted({groups.get(path, 'removed') for _, path in changes})
    if touched:
        print('Review the README lines for these groups: ' + ', '.join(touched))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=['check', 'apply'])
    parser.add_argument('--source', type=Path,
                        default=Path(os.environ.get('LEADBUSTER_DIR', '/var/www/html/leadbuster')))
    parser.add_argument('--laravel', type=Path, default=HARNESS / 'laravel')
    parser.add_argument('--ref', default='main')
    args = parser.parse_args()

    if not (args.source / '.git').exists():
        print(f'error: no Leadbuster checkout at {args.source}', file=sys.stderr)
        return 3
    try:
        wanted, groups, unlisted = plan(args.source, args.laravel, args.ref)
    except ManifestError as error:
        print(f'error: {error}', file=sys.stderr)
        return 2

    changes = diff(args.source, args.laravel, wanted)
    report(changes, unlisted, uncommitted(args.source, wanted, args.ref))
    if unlisted:
        print('Not synced: list every unlisted file first.')
        return 1
    if args.mode == 'check':
        if changes:
            print(f'{len(changes)} file(s) differ from Leadbuster {args.ref}. Run: tools/laravel/sync.py apply')
            return 1
        print(f'laravel/files matches Leadbuster {args.ref}.')
        return 0
    apply(args.source, args.laravel, wanted, groups, changes, args.ref)
    print(f'Synced {len(changes)} file(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
