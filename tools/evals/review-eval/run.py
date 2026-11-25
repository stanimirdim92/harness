#!/usr/bin/env python3
"""Review eval: does /review catch bugs that really shipped?

A bugfix commit in the project's history holds its own answer key. Blame on
the lines it changed finds the commit that introduced the bug. The eval runs
a standalone `/review` on that commit, on the code as it was before it, and
checks whether a BLOCKER or REQUIRED finding points at those lines and names
the defect. A case's `defect` terms say what the finding must be about: a
finding near the lines that is about something else is LOCATED, not CAUGHT.
A case with no `defect` terms can never score CAUGHT; add them with --defect.

A clean case is a commit nobody had to fix. There the eval counts the
blocking findings: each one is noise (ADR 0093).

Usage:
    run.py --new fix-feed-order --repo ~/app --fix <sha> --defect 'order|sort'  # case from a bugfix
    run.py --new quiet-ui --repo ~/app --clean <sha>           # case from a clean commit
    run.py --fixture fix-feed-order --fixture quiet-ui --repo ~/app --output ./before
    run.py --fixture ... --repo ~/app --output ./after --baseline ./before/results.json
    run.py --fixture fix-feed-order --findings review.sarif    # judge a saved SARIF (free)
    run.py --all --tag tenant --repo ~/app --output ./tenant   # every case carrying a tag

A case carries `tags` (what behavior it exercises) and a `split`: `optimization`,
the cases you read while changing the harness, or `holdout`, the cases you do
not. A change is accepted only when no holdout case the baseline passed is lost
(ADR 0117). Producing drives the real model and costs money: never in CI.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
TOLERANCE = 3          # a finding within this many lines of a target line counts
BLOCKING = {'BLOCKER', 'REQUIRED'}
REVIEW_TOOLS = ('Read', 'Glob', 'Grep', 'Write', 'Task', 'Agent', 'Skill',
                'Bash(git *)', 'Bash(mkdir *)', 'Bash(python3 *)')

sys.path.insert(0, str(HERE.parent))
import sandbox  # noqa: E402
import todo  # noqa: E402

_spec = importlib.util.spec_from_file_location('spec_eval', HERE.parent / 'spec-eval' / 'run.py')
spec_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spec_eval)


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=check).stdout


# ---------------------------------------------------------------- building a case

HUNK = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@', re.M)


def fix_lines(repo, fix):
    """{path: [line, ...]} in fix^: the lines the fix removed or changed, and the
    line at each insertion point."""
    out = git(repo, 'diff', '-U0', '--no-color', '--no-ext-diff', f'{fix}^', fix)
    lines, path = {}, None
    for line in out.splitlines():
        if line.startswith('--- '):
            path = None if line[4:] == '/dev/null' else line[6:]
        elif path and (m := HUNK.match(line)):
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            span = range(start, start + count) if count else range(max(start, 1), max(start, 1) + 1)
            lines.setdefault(path, []).extend(span)
    return lines


def blame(repo, rev, path, line):
    """(commit, original path, original line) for one line of path at rev."""
    out = git(repo, 'blame', '--porcelain', '-L', f'{line},{line}', rev, '--', path, check=False)
    head = out.splitlines()[0].split() if out else []
    if len(head) < 2:
        return None
    original = next((l[9:] for l in out.splitlines() if l.startswith('filename ')), path)
    return head[0], original, int(head[1])


def bug_case(repo, fix, bug=None):
    """The case for a bugfix: the commit that introduced the bug, and the lines
    of that commit's version the fix later changed."""
    blamed = [b for path, nums in fix_lines(repo, fix).items() for n in nums
              if (b := blame(repo, f'{fix}^', path, n))]
    if not blamed:
        raise SystemExit('review-eval: the fix changes no line that blame can trace')
    bug = bug or Counter(c for c, _, _ in blamed).most_common(1)[0][0]
    bug = git(repo, 'rev-parse', bug).strip()
    targets = {}
    for commit, path, line in blamed:
        if commit == bug:
            targets.setdefault(path, []).append(line)
    if not targets:
        raise SystemExit(f'review-eval: no line the fix changed comes from {bug[:10]}')
    return {'kind': 'bug', 'change': bug, 'fix': git(repo, 'rev-parse', fix).strip(),
            'targets': {p: sorted(set(v)) for p, v in targets.items()}}


def clean_case(repo, commit):
    return {'kind': 'clean', 'change': git(repo, 'rev-parse', commit).strip(), 'targets': {}}


def load(name):
    return json.loads((FIXTURES / name / 'case.json').read_text())


def selected(names, every=False, tags=(), split=None):
    """The cases to run: the named ones, or every case under fixtures/, narrowed to those carrying
    any of `tags` and, with `split`, to that split. A case without a split is optimization."""
    if every:
        names = sorted(p.parent.name for p in FIXTURES.glob('*/case.json'))
    out = []
    for name in names:
        case = load(name)
        if tags and not set(tags) & set(case.get('tags', [])):
            continue
        if split and case.get('split', 'optimization') != split:
            continue
        out.append(name)
    return out


# ---------------------------------------------------------------- judging

def sarif_findings(text):
    """[(path, line or None, disposition, text)] from a review SARIF file. The
    text is the message plus every string property, so a defect term can match
    the claim, the failure scenario or the class."""
    found = []
    for run in json.loads(text).get('runs', []):
        for result in run.get('results', []):
            props = result.get('properties', {})
            disp = props.get('disposition') or \
                {'error': 'BLOCKER', 'warning': 'REQUIRED', 'note': 'ADVISORY'}.get(result.get('level'), '?')
            words = ' '.join([result.get('ruleId') or '', (result.get('message') or {}).get('text') or '',
                              *(str(v) for v in props.values() if isinstance(v, str))])
            locs = result.get('locations') or [{}]
            for loc in locs:
                phys = loc.get('physicalLocation', {})
                found.append((phys.get('artifactLocation', {}).get('uri'),
                              phys.get('region', {}).get('startLine'), disp, words))
    return found


MARKDOWN = re.compile(r'^\s*-\s*\[([A-Z]+-\d+)\]\s*\[?`?([\w./-]+\.\w+):(\d+)', re.M)


def markdown_findings(text):
    """Fallback when no SARIF was written: `- [CODE-1] [path:line] ...` lines,
    with the disposition taken from the nearest heading above."""
    found, disp = [], '?'
    for line in text.splitlines():
        heading = re.match(r'^#+\s*(BLOCKER|REQUIRED|ADVISORY)\b', line.strip())
        if heading:
            disp = heading.group(1)
        elif (m := MARKDOWN.match(line)):
            found.append((m.group(2), int(m.group(3)), disp, line))
    return found


COUNT_LINE = re.compile(r'Findings:\s*(\d+)\s*BLOCKER\s*·\s*(\d+)\s*REQUIRED\s*·\s*(\d+)\s*ADVISORY')


def review_findings(meta, sarifs):
    """(findings, source) from a finished review, or RuntimeError.

    A review that did not finish proves nothing: an error result, REVIEW
    BLOCKED, empty output or a count line the findings do not back up must not
    score as a quiet review. Zero findings count only when the report says so."""
    result = meta.get('result') or ''
    if meta.get('is_error') or meta.get('subtype', 'success') != 'success':
        raise RuntimeError(f'review did not finish ({meta.get("subtype") or "is_error"}): {result[:300]}')
    if 'REVIEW BLOCKED' in result:
        raise RuntimeError(f'review blocked: {result[:300]}')
    if sarifs:
        try:
            return [f for s in sarifs for f in sarif_findings(s)], 'sarif'
        except ValueError as err:
            raise RuntimeError(f'unreadable SARIF: {err}')
    findings = markdown_findings(result)
    if findings:
        return findings, 'markdown'
    counts = COUNT_LINE.search(result)
    if counts and sum(map(int, counts.groups())):
        raise RuntimeError(f'report counts {"/".join(counts.groups())} findings, none could be read: {result[:300]}')
    if counts or 'Nothing to fix' in result:
        return [], 'markdown'
    raise RuntimeError(f'no SARIF and no findings report in the output: {result[:300]}')


def judge(case, findings):
    """{'caught', 'located', 'caught_any', 'blocking', 'findings', 'by'} for one case.

    caught: a BLOCKER or REQUIRED finding near a target line whose text names
    the defect (any `defect` term, a case-insensitive regex). located: such a
    finding near the lines, about anything. Location alone proved nothing on
    LD-585: every nearby finding was about another part of the change."""
    terms = [re.compile(t, re.I) for t in case.get('defect', [])]

    def near(f):
        targets = case['targets'].get(f[0]) or []
        return f[1] is not None and any(abs(f[1] - t) <= TOLERANCE for t in targets)

    def named(f):
        return bool(terms) and any(t.search(f[3] if len(f) > 3 else '') for t in terms)

    blocking = [f for f in findings if f[2] in BLOCKING]
    caught = [f for f in blocking if near(f) and named(f)]
    return {'caught': bool(caught),
            'located': any(near(f) for f in blocking),
            'caught_any': any(near(f) and named(f) for f in findings),
            'blocking': len(blocking), 'findings': len(findings),
            'by': sorted({(f[3] or '').split()[0] for f in caught if f[3]}) if caught else []}


def item(case, result):
    """The pass/fail item a case contributes to a paired comparison."""
    return result['caught'] if case['kind'] == 'bug' else result['blocking'] == 0


def compare(baseline, items, splits):
    """The paired verdict, with the holdout rule on top: a holdout case the baseline passed and this run
    lost makes the change WORSE whatever the optimization cases gained. Returns (pair, word, why, lost holdout)."""
    pair = spec_eval.paired(baseline, items)
    lost = [n for n in pair['regressions'] if splits.get(n) == 'holdout']
    word, why = spec_eval.verdict(pair)
    if lost:
        word, why = 'WORSE', 'a holdout case the baseline passed is now lost'
    return pair, word, why, lost


def tally(names, items, kinds):
    """'bugs a/b, clean c/d' over `names`; the parts that exist."""
    parts = []
    for kind, label in (('bug', 'bugs'), ('clean', 'clean')):
        of = [n for n in names if kinds.get(n) == kind]
        if of:
            parts.append(f'{label} {sum(bool(items.get(n)) for n in of)}/{len(of)}')
    return ', '.join(parts)


# ---------------------------------------------------------------- producing

def keep(out, meta, sarifs):
    """Save what the review produced, so a result can be read after the run:
    the report text, the run metadata and every SARIF file."""
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.md').write_text(meta.get('result') or '')
    (out / 'meta.json').write_text(json.dumps({k: v for k, v in meta.items() if k != 'result'}, indent=2) + '\n')
    for s in sarifs:
        (out / s.name).write_text(s.read_text())


def produce(case, repo, budget, out=None):
    """Run a standalone /review on the case's change, in a throwaway project.
    With `out`, the report, metadata and SARIF are copied there first."""
    with tempfile.TemporaryDirectory() as tmp:
        project = sandbox.export_repo(Path(tmp) / 'project', repo, f'{case["change"]}^')
        sandbox.install_harness(project)
        sandbox.commit_baseline(project)
        patch = git(repo, 'diff', '--binary', '--no-ext-diff', f'{case["change"]}^', case['change'])
        subprocess.run(['git', 'apply', '--index'], input=patch, text=True, cwd=project, check=True)
        subprocess.run(['git', '-c', 'user.email=f@f', '-c', 'user.name=f', 'commit', '-qm', 'Change under review'],
                       cwd=project, check=True, capture_output=True)
        prompt = ('/review HEAD~1..HEAD\n\nThis is a standalone review of the last commit; there is no '
                  'BUILD handoff, spec or ticket. Use REVIEW-EVAL as the ticket id for the SARIF file.')
        meta = sandbox.run_session(sandbox.session_args(prompt, budget, allowed_tools=REVIEW_TOOLS), project,
                                   trace=(out or Path(tmp)) / 'trace.jsonl')
        sarifs = sorted((project / 'docs' / 'reviews').glob('*.sarif'))
        if out:
            keep(out, meta, sarifs)
        findings, source = review_findings(meta, [s.read_text() for s in sarifs])
        return findings, meta, source


# ---------------------------------------------------------------- suite

def kept_cost(folder):
    """What a review that raised still spent, or None when it cannot be known. `keep()` saves `meta.json`
    once the session ended. A session that exited non-zero left only its trace, which ends with the
    `result` event; one that timed out left neither."""
    folder = Path(folder)
    try:
        return json.loads((folder / 'meta.json').read_text()).get('total_cost_usd') or 0
    except (OSError, ValueError):
        pass
    try:
        lines = (folder / 'trace.jsonl').read_text().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get('type') == 'result':
            return event.get('total_cost_usd')
    return None


def verdict_word(kind, result):
    if kind == 'bug':
        return 'CAUGHT' if result['caught'] else 'LOCATED' if result['located'] else 'MISSED'
    return 'QUIET' if result['blocking'] == 0 else 'NOISY'


LOG = HERE.parents[2] / 'docs' / 'observation-log.md'
MIN_SHA = 7   # a shorter prefix does not name a commit


def shipped_bug(text, sha):
    """The row of the observation log's "Shipped bugs" table whose fix-commit column names `sha`, as
    `{'bug', 'fix'}` (the cell texts), or None. The column holds a short sha, so `sha` names it when
    either is a prefix of the other. Prose and other tables do not count."""
    for row in todo.log_table(text, 'Shipped bugs') or []:
        if 'bug' not in row or 'fix commit' not in row:
            continue
        fix = row['fix commit']
        if len(sha) >= MIN_SHA and any(t.startswith(sha) or sha.startswith(t)
                                       for t in re.findall(rf'\b[0-9a-f]{{{MIN_SHA},40}}\b', fix)):
            return {'bug': row['bug'], 'fix': fix}
    return None


def creation_flags(parser):
    """The flags that make a case; `run.py --new` and `bugs add` take the same."""
    parser.add_argument('--new', metavar='NAME')
    parser.add_argument('--fix', help='with --new: the bugfix commit')
    parser.add_argument('--bug', help='with --new --fix: the commit that introduced the bug (default: found by blame)')
    parser.add_argument('--clean', help='with --new: a commit nobody had to fix')
    parser.add_argument('--tag', action='append', default=[],
                        help='with --new: a behavior tag for the case; otherwise run only cases carrying any given tag')
    parser.add_argument('--holdout', action='store_true', help='with --new: the case is holdout, never read while tuning')
    parser.add_argument('--defect', action='append', default=[],
                        help='with --new --fix: a regex the finding must contain to count as caught (repeatable)')


def create_case(args, description=None):
    """Write `fixtures/<args.new>/case.json` for a bugfix (`args.fix`) or a clean commit (`args.clean`)."""
    case = bug_case(args.repo, args.fix, args.bug) if args.fix else clean_case(args.repo, args.clean)
    out = FIXTURES / args.new
    out.mkdir(parents=True, exist_ok=True)
    case.update(tags=sorted(set(args.tag)), split='holdout' if args.holdout else 'optimization')
    if description:
        case['description'] = description
    if case['kind'] == 'bug':
        case['defect'] = args.defect
        if not args.defect:
            print('Warning: no --defect terms. The case cannot score CAUGHT until you add a '
                  '"defect" list to case.json.', file=sys.stderr)
    (out / 'case.json').write_text(json.dumps({'name': args.new, **case}, indent=2) + '\n')
    where = ', '.join(f'{p} ({len(v)} line(s))' for p, v in case['targets'].items()) or 'none (clean case)'
    print(f'Case {out}: {case["kind"]}, {case["split"]}, tags {", ".join(case["tags"]) or "-"}, '
          f'change {case["change"][:10]}, targets: {where}.')
    return 0


def add_case(argv):
    """`eval.py bugs add`: `run.py --new`'s arguments, and `--from-log <fix sha>` to take the fix and the
    description from the "Shipped bugs" row. A bugfix needs a `--defect` term. Exit 2 when it cannot
    build the case."""
    parser = argparse.ArgumentParser(prog='eval.py bugs add', description=add_case.__doc__.split('\n')[0])
    creation_flags(parser)
    parser.add_argument('--repo', type=Path, required=True, help='the project the fix is in')
    parser.add_argument('--from-log', metavar='SHA', help='the fix commit of a "Shipped bugs" row')
    parser.add_argument('--log', type=Path, default=LOG, help='the observation log (default: docs/observation-log.md)')
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return stop.code or 0
    description = None
    if args.from_log:
        if args.fix or args.clean:
            print('--from-log gives the fix commit: leave out --fix and --clean', file=sys.stderr)
            return 2
        try:
            text = args.log.read_text()
        except OSError as err:
            print(f'cannot read the observation log: {err}', file=sys.stderr)
            return 2
        row = shipped_bug(text, args.from_log)
        if row is None:
            print(f'no Shipped bugs row names {args.from_log}', file=sys.stderr)
            return 2
        args.fix, description = args.from_log, row['bug']
        args.new = args.new or f'fix-{args.from_log[:8]}'
    if not args.new or not (args.fix or args.clean):
        print('bugs add needs --from-log, or --new with --fix or --clean', file=sys.stderr)
        return 2
    if args.fix and not args.defect:
        print('a bugfix case needs at least one --defect term: the regex a finding must match to count as caught',
              file=sys.stderr)
        return 2
    return create_case(args, description)


class BugsSuite:
    """The shipped-bug cases as a suite for the eval core (`core.py` describes the interface). A trial is
    one `/review` of one case in `repo`, judged by `judge()`. A bug trial passes when it is CAUGHT; a
    clean trial passes when it has no BLOCKER or REQUIRED finding."""
    name = 'bugs'
    kind = 'case'
    model = None

    def __init__(self, repo=None, budget=10):
        self.repo, self.budget = repo, budget
        self.spent = {}

    def all_cases(self):
        out = []
        for name in selected([], every=True):
            case = load(name)
            out.append({'id': name, 'split': case.get('split', 'optimization'), 'tags': case.get('tags', []),
                        'kind': case['kind']})
        return out

    def instruction_hashes(self, cases):
        return sandbox.harness_hashes()

    def add(self, argv):
        return add_case(argv)

    def run_trial(self, case, folder):
        """The core retries a trial that raises, so what the first attempt spent comes off the budget of the retry."""
        full = load(case['id'])
        if full['kind'] == 'bug' and not full.get('defect'):
            print(f'  {case["id"]}: no "defect" terms in case.json; it can score LOCATED at best', file=sys.stderr)
        key = str(folder)
        left = float(self.budget) - self.spent.get(key, 0)
        if left <= 0:
            raise RuntimeError('the trial budget was spent by the first attempt')
        try:
            findings, meta, source = produce(full, self.repo, left, Path(folder))
        except Exception:
            cost = kept_cost(folder)
            self.spent[key] = self.spent.get(key, 0) + (float(self.budget) if cost is None else cost)
            raise
        result = judge(full, findings)
        trace = Path(folder) / 'trace.jsonl'
        leaked, leaks = sandbox.audit(trace) if trace.is_file() else (False, [])
        return {'checks': None, 'kind': full['kind'], 'verdict': verdict_word(full['kind'], result),
                'source': source, 'cost_usd': meta.get('total_cost_usd'), 'duration_ms': meta.get('duration_ms'),
                'leaked': leaked, 'leaks': leaks,
                **{k: result[k] for k in ('caught', 'located', 'blocking', 'findings', 'by')}}

    def state(self, trial):
        """A LEAKED trial fails whatever the judge said (REQ-009)."""
        if not trial.get('kind'):
            return 'errored'
        return 'pass' if item(trial, trial) and not trial.get('leaked') else 'fail'


# ---------------------------------------------------------------- cli

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    creation_flags(parser)
    parser.add_argument('--fixture', action='append', default=[])
    parser.add_argument('--all', action='store_true', help='every case under fixtures/')
    parser.add_argument('--split', choices=('optimization', 'holdout'), help='run only this split')
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--findings', type=Path, help='judge this SARIF file instead of producing (free; one fixture)')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--budget', default='10')
    args = parser.parse_args(argv)

    if args.new:
        if not args.repo or not (args.fix or args.clean):
            parser.error('--new needs --repo and --fix or --clean')
        return create_case(args)

    if not args.fixture and not args.all:
        parser.error('give --new, or one or more --fixture, or --all')
    names = selected(args.fixture, args.all, args.tag, args.split)
    if not names:
        parser.error('no case matches')
    results, items, spent, errored = {}, {}, 0.0, []
    kinds, splits, tags = {}, {}, {}
    for name in names:
        case = load(name)
        kinds[name], splits[name], tags[name] = case['kind'], case.get('split', 'optimization'), case.get('tags', [])
        if case['kind'] == 'bug' and not case.get('defect'):
            print(f'  {name}: no "defect" terms in case.json; it can score LOCATED at best', file=sys.stderr)
        if args.findings:
            findings, source = sarif_findings(args.findings.read_text()), 'given'
        else:
            if not args.repo:
                parser.error('producing needs --repo')
            try:
                findings, meta, source = produce(case, args.repo, args.budget,
                                                 args.output / name if args.output else None)
            except RuntimeError as err:
                # No usable review: leave the case unscored, never count it quiet.
                results[name] = {'kind': case['kind'], 'error': str(err)}
                errored.append(name)
                print(f'  {name:<32} {case["kind"]:<6} {"ERRORED (not scored)":<24} {str(err)[:200]}')
                continue
            spent += meta.get('total_cost_usd', 0) or 0
        result = judge(case, findings)
        results[name] = {**result, 'kind': case['kind'], 'source': source, 'split': splits[name], 'tags': tags[name]}
        items[name] = item(case, result)
        mark = ('CAUGHT' if result['caught'] else 'LOCATED, not named' if result['located'] else 'missed') \
            if case['kind'] == 'bug' else \
            ('quiet' if result['blocking'] == 0 else f'{result["blocking"]} blocking finding(s)')
        print(f'  {name:<32} {case["kind"]:<6} {mark:<24} findings {result["findings"]} ({source})')

    bugs = [n for n in items if results[n]['kind'] == 'bug']
    clean = [n for n in items if results[n]['kind'] == 'clean']
    if bugs:
        print(f'Bugs caught: {sum(results[n]["caught"] for n in bugs)}/{len(bugs)}')
    if clean:
        print(f'Clean cases quiet: {sum(results[n]["blocking"] == 0 for n in clean)}/{len(clean)}')
    holdout = [n for n in items if splits[n] == 'holdout']
    if holdout:
        print(f'Holdout: {tally(holdout, items, kinds)}')
    every_tag = sorted({t for n in items for t in tags[n]})
    if every_tag:
        print('By tag: ' + '; '.join(f'{t} {tally([n for n in items if t in tags[n]], items, kinds)}' for t in every_tag))
    if errored:
        print(f'Errored, not scored: {len(errored)} ({", ".join(errored)})')
    if spent:
        print(f'Cost: ${spent:.2f}')

    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'results.json').write_text(json.dumps(
            {'results': items, 'splits': splits, 'tags': tags, 'detail': results}, indent=2) + '\n')
    if args.baseline:
        base = json.loads(args.baseline.read_text())['results']
        pair, word, why, lost = compare(base, items, splits)
        for n in pair['wins']:
            print(f'  gained {n}')
        for n in pair['regressions']:
            print(f'  lost   {n}' + (' (holdout)' if n in lost else ''))
        if holdout:
            before = sum(bool(base.get(n)) for n in holdout if n in base)
            print(f'Holdout: {before}/{len(holdout)} -> {sum(bool(items[n]) for n in holdout)}/{len(holdout)}')
        print(f'{word}: {why}')
        return 0 if word in ('BETTER', 'SAME') and not errored else 1
    return 1 if errored else 0


if __name__ == '__main__':
    sys.exit(main())
