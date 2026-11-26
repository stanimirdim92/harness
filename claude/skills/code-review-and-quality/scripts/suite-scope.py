#!/usr/bin/env python3
"""Does this change need the full test suite? (ADR 0154)

The full suite catches a regression in code the change does not touch. It is
needed only when the change can reach that code. This script decides from the
diff, the same way every time, so the verifier never runs the suite on its own
judgment. It answers yes when a changed file:

- is a dependency manifest or lockfile;
- is a migration, or sits under `config/`, `bootstrap/` or `routes/`;
- is test configuration or a shared test helper;
- matches a glob under a "## Full suite" heading in a base-branch REVIEW.md
  (one glob per bullet in backticks, as for "## Always a person");
- is a PHP class that production code outside its module references. A
  module is `Modules/<Name>`, `modules/<Name>` or `packages/<Name>`;
  otherwise it is the top-level directory. Other languages rely on the
  REVIEW.md list.

Otherwise it lists the focused tests: the changed test files and every test
file that names a changed PHP class.

Usage:
    suite-scope.py --base origin/main            # changed files: base...HEAD
    suite-scope.py --base <sha> --json

Exit: 0 focused tests are enough · 1 run the full suite · 2 usage or git error.
"""
import argparse
import fnmatch
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath

_spec = importlib.util.spec_from_file_location('always_person', Path(__file__).with_name('always-person.py'))
ap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ap)

HEADING = re.compile(r'^##\s+Full suite\s*$', re.I | re.M)

MANIFESTS = {
    'composer.json', 'composer.lock', 'package.json', 'package-lock.json', 'yarn.lock',
    'pnpm-lock.yaml', 'pyproject.toml', 'poetry.lock', 'uv.lock', 'go.mod', 'go.sum',
    'Cargo.toml', 'Cargo.lock', 'Gemfile', 'Gemfile.lock',
}
SHARED_DIRS = ('config/', 'bootstrap/', 'routes/', 'tests/Support/', 'tests/Helpers/', 'tests/Datasets/')
TEST_CONFIG = (
    'phpunit.xml*', 'tests/Pest.php', 'tests/TestCase.php', 'tests/bootstrap.php',
    '.env.testing', 'conftest.py', '*/conftest.py', 'pytest.ini',
    'vitest.config.*', 'jest.config.*',
)
MODULE_ROOTS = {'Modules', 'modules', 'packages'}
NAMESPACE = re.compile(r'^\s*namespace\s+([\w\\]+)\s*;', re.M)
CLASS = re.compile(r'^\s*(?:(?:abstract|final|readonly)\s+)*(?:class|interface|trait|enum)\s+(\w+)', re.M)


def builtin_reason(path):
    """Why a path alone needs the full suite, or None."""
    p = PurePosixPath(path)
    if p.name in MANIFESTS:
        return 'dependency manifest or lockfile'
    shared = {'migrations', 'factories', 'seeders'} & set(p.parts[:-1])
    if shared:
        return {'migrations': 'migration', 'factories': 'model factory', 'seeders': 'seeder'}[shared.pop()]
    if path.startswith(SHARED_DIRS):
        return f'shared directory {path.split("/")[0]}/' if not path.startswith('tests/') else 'shared test helper'
    if any(fnmatch.fnmatch(path, g) for g in TEST_CONFIG):
        return 'test configuration'
    return None


def module_of(path):
    parts = PurePosixPath(path).parts
    if len(parts) > 2 and parts[0] in MODULE_ROOTS:
        return '/'.join(parts[:2]) + '/'
    return parts[0] + '/' if len(parts) > 1 else ''


def php_class(base, path):
    """(namespace, class) a PHP file declares, read at HEAD or, for a deleted file, at base."""
    rc, text = ap.git('show', f'HEAD:{path}')
    if rc:
        rc, text = ap.git('show', f'{base}:{path}')
    if rc:
        return None
    ns, cls = NAMESPACE.search(text), CLASS.search(text)
    return (ns.group(1), cls.group(1)) if ns and cls else None


def is_test(path):
    p = PurePosixPath(path)
    return 'tests' in p.parts or p.name.endswith('Test.php')


def references(base, path):
    """(production files outside path's module, test files) naming its class, at HEAD."""
    declared = php_class(base, path)
    if not declared:
        return [], []
    ns, cls = declared

    def grep(text):
        rc, out = ap.git('grep', '-l', '-F', text, 'HEAD', '--', '*.php')
        return {line.split(':', 1)[1] for line in out.splitlines() if ':' in line} if rc == 0 else set()

    files = grep(f'{ns}\\{cls}')
    # A grouped import, `use Ns\{A, B};`, names the class without its namespace.
    group = re.compile(r'use\s+' + re.escape(ns) + r'\\\{[^}]*\b' + re.escape(cls) + r'\b')
    for f in grep(f'{ns}\\{{') - files:
        rc, text = ap.git('show', f'HEAD:{f}')
        if rc == 0 and group.search(text):
            files.add(f)
    files = sorted(files)
    module = module_of(path)
    tests = [f for f in files if is_test(f)]
    outside = [f for f in files if f != path and f not in tests and not f.startswith(module)]
    return outside, tests


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--base', required=True)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    rc, out = ap.git('diff', '--name-only', '--no-renames', '-z', f'{args.base}...HEAD')
    if rc:
        print(f'suite-scope: cannot diff {args.base}...HEAD', file=sys.stderr)
        return 2
    changed = [p for p in out.split('\0') if p]
    globs = ap.review_globs(args.base, changed, HEADING)

    reasons, focused = {}, {f for f in changed if is_test(f) and f.endswith('.php')}
    for f in changed:
        why = builtin_reason(f)
        if not why:
            hit = [g for g in globs if ap.matches(f, g)]
            why = f'REVIEW.md "Full suite" ({", ".join(hit)})' if hit else None
        if not why and f.endswith('.php') and not is_test(f):
            refs, tests = references(args.base, f)
            focused.update(tests)
            why = f'class used outside {module_of(f) or "its module"} ({", ".join(refs[:3])}{", ..." if len(refs) > 3 else ""})' if refs else None
        if why:
            reasons[f] = why

    if args.json:
        print(json.dumps({'full': bool(reasons), 'reasons': reasons, 'focused': sorted(focused)}, indent=2))
    elif not reasons:
        print(f'Full suite: no. None of {len(changed)} changed file(s) reaches code outside its module.')
        print(f'Focused tests ({len(focused)}):')
        for f in sorted(focused):
            print(f'  {f}')
    else:
        print(f'Full suite: yes, because of {len(reasons)} file(s):')
        for f, why in sorted(reasons.items()):
            print(f'  {f}   ({why})')
    return 1 if reasons else 0


if __name__ == '__main__':
    sys.exit(main())
