"""The eval core: where runs are stored, how trials run, and how a run is judged.

A suite knows how to run one trial of one case. The core owns everything
else: the run folder, the trials and their retry, `results.json`, the
baseline, the verdict and the report. The public functions print for a
person and return an exit code: 0 and 1 are the verdict, 2 means the run could
not be made or could not be judged.

Suite interface (fixed once; a later task does not change it without a replan)
------------------------------------------------------------------------------
    name                 'gates', 'tasks' or 'bugs'. Names the results folder.
    kind                 'case' or 'check'. What an item is. For 'case' (gates,
                         bugs) an item is the case. For 'check' (tasks) an item
                         is a key of a trial's `checks` map.
    any_loss_is_worse    Optional, default False. True for gates: any lost
                         case makes the verdict WORSE (REQ-005 rule 1).
    model                Optional, default None. The model the suite runs.
    instruction_hashes(cases)
                         Optional. `{path: sha256}` of the instruction files
                         the cases read, or None when unknown.
    run_trial(case, folder) -> dict
                         Runs one trial in `folder`, which exists. Returns the
                         trial record: `checks` (`{id: bool}` or None),
                         `cost_usd`, `duration_ms`, and any other field the
                         suite wants kept. It raises on a timeout or a CLI
                         error. The core records that as ERRORED.
    state(trial) -> 'pass' | 'fail' | 'errored'
                         The state of a returned trial. Empty output is
                         'errored'. For 'check' suites 'pass' means every check
                         passed.

A case is a dict `{'id', 'split', 'tags'}`. A split of 'holdout' marks a
holdout case (REQ-005 rule 1).

results.json, schema 1
----------------------
    schema                1
    suite                 suite name
    run                   run folder name, `<YYYY-MM-DD-HHMMSS>-<sha7>`
    item_kind             'case' or 'check'
    harness_commit        sha7 of HEAD
    dirty                 true when `claude/` has uncommitted changes
    instruction_hashes    `{path: sha256}` or null
    model                 string or null
    trials                trials requested per case
    started               ISO time, seconds
    duration_ms           integer
    cost_usd              sum of the known trial costs, or null when none known
    trials_without_cost   how many trials had a null cost
    cases[]
        id, split, tags
        semantic_review   'pending', or {'verdict': 'ok'|'bad', 'note', 'date'}
        result            {state: 'PASS'|'FLAKY'|'FAIL'|null, passed, scored,
                           items: {item: state}, counts: {item: [passed, scored]}}
                          `passed` counts trials whose state is 'pass'. `scored`
                          leaves out ERRORED trials. `state` is null when no
                          trial was scored.
        trials[]          n, state, checks, cost_usd, duration_ms, folder
                          (relative to the run folder), retried, error, and
                          every extra field the suite returned
A field the suite cannot know is null, never left out.

Layout: `tools/evals/results/<suite>/<run>/` holds `results.json`,
`report.md` and one `<case>/t<n>/` folder per trial. A trial that was retried
keeps its first attempt in `<case>/t<n>-attempt1/`. The file
`tools/evals/results/<suite>/BASELINE` holds the baseline run's folder name.
"""
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRIALS = 3
RESULTS = 'tools/evals/results'
FAIL, FLAKY, PASS = 'FAIL', 'FLAKY', 'PASS'
RANK = {FAIL: 0, FLAKY: 1, PASS: 2}


class Refused(Exception):
    """The core cannot continue. The message says why; the exit code is 2."""


def run_name(now, commit):
    return f'{now:%Y-%m-%d-%H%M%S}-{commit}'


def _git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)


# ---------------------------------------------------------------- states

def _state(passed, scored):
    if not scored:
        return None
    return PASS if passed == scored else FAIL if passed == 0 else FLAKY


def case_result(kind, case_id, trials):
    """Roll the trials of one case into its result. ERRORED trials are not scored."""
    scored = [t for t in trials if t['state'] != 'errored']
    passed = sum(t['state'] == 'pass' for t in scored)
    if kind == 'case':
        counts = {case_id: [passed, len(scored)]}
    else:
        counts = {}
        for trial in scored:
            for item, ok in (trial.get('checks') or {}).items():
                counts.setdefault(item, [0, 0])
                counts[item][0] += bool(ok)
                counts[item][1] += 1
    return {'state': _state(passed, len(scored)), 'passed': passed, 'scored': len(scored),
            'items': {item: _state(*pair) for item, pair in sorted(counts.items())},
            'counts': {item: pair for item, pair in sorted(counts.items())}}


# ---------------------------------------------------------------- verdict

def _items(doc):
    items = {}
    for entry in doc['cases']:
        holdout = doc['item_kind'] == 'case' and entry['split'] == 'holdout'
        for name, state in entry['result']['items'].items():
            items[name] = {'state': state, 'holdout': holdout, 'case': entry['id']}
    return items


def compare(base_doc, run_doc):
    """Compare every item the run ran with the same item in the baseline.
    An item the baseline lacks is new. An item with no scored trial is unscored."""
    base, run = _items(base_doc), _items(run_doc)
    diff = {'gained': [], 'lost': [], 'new': [], 'unscored': [], 'unchanged': 0, 'holdout_lost': []}
    for name in sorted(run):
        state, before = run[name]['state'], base.get(name, {}).get('state')
        if state is None:
            diff['unscored'].append(name)
        elif before is None:
            diff['new'].append(name)
        elif RANK[state] > RANK[before]:
            diff['gained'].append(name)
        elif RANK[state] < RANK[before]:
            diff['lost'].append(name)
            if run[name]['holdout'] and before == PASS:
                diff['holdout_lost'].append(name)
        else:
            diff['unchanged'] += 1
    diff['compared'] = len(diff['gained']) + len(diff['lost']) + diff['unchanged']
    return diff


def verdict(diff, any_loss_is_worse=False):
    """The first rule that applies (REQ-005). Returns `(word, reason)`."""
    if any_loss_is_worse and diff['lost']:
        return 'WORSE', 'a case the baseline had higher is now lower'
    if diff['holdout_lost']:
        return 'WORSE', 'a holdout case the baseline had at PASS is no longer PASS'
    if diff['lost'] and len(diff['lost']) >= len(diff['gained']):
        return 'NOT BETTER', 'as many or more items lost than gained'
    if len(diff['gained']) > len(diff['lost']):
        return 'BETTER', 'more items gained than lost'
    return 'SAME', 'no item changed'


# ---------------------------------------------------------------- report

def _money(value):
    return 'unknown' if value is None else f'${value:.2f}'


def _span(ms):
    if ms is None:
        return 'unknown'
    return f'{ms / 60000:.1f} min' if ms >= 60000 else f'{ms / 1000:.1f} s'


def _names(items, counts):
    return ', '.join(f'{n} ({counts[n][0]}/{counts[n][1]})' if n in counts else n for n in items) or 'none'


def eval_line(doc, run_dir, base=None, word=None, selection=None):
    """The `Eval:` trailer line of the gates report (REQ-016). A baseline is compared on the cases the run ran."""
    def tally(cases):
        return sum(c['result']['state'] == PASS for c in cases), sum(c['result']['state'] == FLAKY for c in cases)

    ran = {c['id'] for c in doc['cases']}
    passed, flaky = tally(doc['cases'])
    total = len(doc['cases'])
    where = f' [{selection}]' if selection else ''
    if base is None:
        return f'Eval: gates{where} {passed}/{total} PASS, flaky {flaky}; {run_dir}'
    before, before_flaky = tally([c for c in base['cases'] if c['id'] in ran])
    return (f'Eval: gates{where} {before}/{total} PASS -> {passed}/{total} PASS, '
            f'flaky {before_flaky} -> {flaky} ({word}); {run_dir}')


def review_eval_line(doc, run_dir, base=None, word=None):
    """The `Review-eval:` trailer line of the bugs report (ADR 0111, `check-rescore.py`). It counts the
    cases at PASS: bug cases, clean cases and holdout cases. The kind of a case comes from its scored
    trials, so a case with none is left out. A baseline is compared on the cases the run ran."""
    kinds = {c['id']: t['kind'] for c in doc['cases'] for t in c['trials'] if t['state'] != 'errored' and t.get('kind')}
    holdout = {c['id'] for c in doc['cases'] if c['split'] == 'holdout'}
    groups = [('bugs', [n for n, kind in kinds.items() if kind == 'bug']),
              ('clean', [n for n, kind in kinds.items() if kind == 'clean']),
              ('holdout', [n for n in kinds if n in holdout])]
    now = {c['id']: c['result']['state'] for c in doc['cases']}
    before = {c['id']: c['result']['state'] for c in base['cases']} if base else None

    def passing(names, states):
        return sum(states.get(n) == PASS for n in names)

    parts = [f'{label} {passing(names, before)}/{len(names)} -> {passing(names, now)}/{len(names)}' if base
             else f'{label} {passing(names, now)}/{len(names)}' for label, names in groups if names]
    return f'Review-eval: {", ".join(parts)}' + (f' ({word})' if base else '') + f'; {run_dir}'


def _leaked_line(doc, run_dir):
    """The trials whose trace named eval files (REQ-009). A suite that audits its traces sets `leaked`."""
    leaked = [t for c in doc['cases'] for t in c['trials'] if t.get('leaked')]
    return 'LEAKED (counted as a fail): ' + (', '.join(f'{run_dir}/{t["folder"]}' for t in leaked) if leaked else 'none')


def _tasks_lines(doc, run_dir):
    """What the `tasks` report adds to the generic one (REQ-020, REQ-031): whether prevention was on,
    the trials that passed every check, and the trials that leaked or stopped early."""
    trials = [(entry, t) for entry in doc['cases'] for t in entry['trials']]
    prevented = bool(trials) and all(t.get('prevention') for _, t in trials)
    head = ('prevention on: Bash reads under claude/evals/ are denied' if prevented
            else 'prevention off: detection only')
    lines = []
    for entry in doc['cases']:
        result = entry['result']
        states = list(result['items'].values())
        lines.append(f'Trials that passed every check: {result["passed"]} of {result["scored"]} ({entry["id"]})')
        lines.append('Checks: ' + ', '.join(f'{states.count(s)} {s}' for s in (PASS, FLAKY, FAIL)))
        every = [n for n, s in result['items'].items() if s == FAIL]
        lines.append(f'Failed in every trial: {", ".join(every) or "none"}')
    lines.append(_leaked_line(doc, run_dir))
    lines += [f'{t["folder"]} stopped: {t["stop_reason"]} at /{t.get("stop_stage")}'
              for _, t in trials if t.get('stop_reason') not in (None, 'complete')]
    lines.append('3 trials measure consistency: a check that passes in some trials and fails in others is FLAKY. '
                 'A change of one trial is not proof of a gain.')
    return head, lines


def render_report(doc, run_dir, base=None, diff=None, word=None, why=None, selection=None, is_baseline=False):
    """The report as text. `run_dir` is the run folder as printed, relative to the repository.
    `is_baseline` is true when the run is the suite's baseline: it has no verdict."""
    suite = doc['suite']
    tasks_head, tasks_lines = _tasks_lines(doc, run_dir) if suite == 'tasks' else (None, [])
    lines = [f'# {suite} run {doc["run"]}',
             f'Harness commit {doc["harness_commit"]}{" (dirty)" if doc["dirty"] else ""}, '
             f'{doc["trials"]} trials per case, {len(doc["cases"])} cases.']
    counts = {n: pair for c in doc['cases'] for n, pair in c['result'].get('counts', {}).items()}
    if is_baseline:
        lines.append(f'This run is the {suite} baseline.')
    elif base is None:
        lines.append(f'No baseline yet for {suite}. These results have no verdict. To promote this run: '
                     f'python3 tools/evals/eval.py baseline {suite} {doc["run"]}')
    else:
        lines.append(f'Verdict: {word}: {why}')
        lines.append(f'Baseline: {base["harness_commit"]}, {base["started"][:10]} ({base["run"]})')
        if doc['instruction_hashes'] is not None and doc['instruction_hashes'] == base['instruction_hashes']:
            lines.append('harness unchanged since baseline: this run measures noise')
    without = doc['trials_without_cost']
    lines.append(f'Cost: {_money(doc["cost_usd"])}' + (f' (baseline {_money(base["cost_usd"])})' if base else '')
                 + (f'; {without} trial{"" if without == 1 else "s"} had no cost' if without else ''))
    lines.append(f'Duration: {_span(doc["duration_ms"])}' + (f' (baseline {_span(base["duration_ms"])})' if base else ''))
    if diff:
        lines += [f'Lost: {_names(diff["lost"], counts)}', f'Gained: {_names(diff["gained"], counts)}']
    flaky = [n for c in doc['cases'] for n, s in c['result']['items'].items() if s == FLAKY]
    lines.append(f'Flaky: {_names(flaky, counts)}')
    if diff:
        lines.append(f'New: {_names(diff["new"], counts)}')
        if diff['unscored']:
            lines.append(f'Unscored (no trial counted): {", ".join(diff["unscored"])}')
    errored = [(t, c) for c in doc['cases'] for t in c['trials'] if t['state'] == 'errored']
    for trial, entry in errored:
        lines.append(f'ERRORED after retry: {run_dir}/{trial["folder"]} ({trial["error"] or "no output"})')
    retried = [(t, c) for c in doc['cases'] for t in c['trials'] if t['retried']]
    if retried:
        passed = [f'{t["folder"]}' for t, _ in retried if t['state'] == 'pass']
        lines.append(f'Retries: {len(retried)} {"retry" if len(retried) == 1 else "retries"}'
                     + (f' ({", ".join(passed)} passed on retry)' if passed else ''))
    pending = [c['id'] for c in doc['cases'] if c['semantic_review'] == 'pending']
    if pending:
        lines.append(f'semantic review pending: {", ".join(pending)}')
    lines += tasks_lines
    changed = set((diff['gained'] + diff['lost']) if diff else [])
    lines.append('Read these:')
    for entry in doc['cases']:
        names = set(entry['result']['items'])
        if not (names & changed or {FLAKY, FAIL} & set(entry['result']['items'].values())):
            continue
        folders = [t['folder'] for t in entry['trials'] if t['state'] != 'pass'] or [entry['id']]
        lines.append(f'- {entry["id"]}: ' + ', '.join(f'{run_dir}/{f}' for f in folders))
    if suite == 'gates':
        lines.append(eval_line(doc, run_dir, None if is_baseline else base, word, selection))
    if suite == 'bugs':
        lines.append(_leaked_line(doc, run_dir))
        lines.append(review_eval_line(doc, run_dir, None if is_baseline else base, word))
    if tasks_head:
        lines.insert(0, tasks_head)
    return '\n'.join(lines)


# ---------------------------------------------------------------- storage

def _results(root):
    return Path(root) / RESULTS


def _runs(root, suite):
    base = _results(root) / suite
    return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def _load(run_dir):
    path = run_dir / 'results.json'
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        doc = None
    if not isinstance(doc, dict) or doc.get('schema') != 1:
        raise Refused(f'{run_dir.name} has no schema 1 results.json; it cannot be used')
    return doc


def _baseline_doc(root, suite):
    pointer = _results(root) / suite / 'BASELINE'
    if not pointer.is_file():
        return None
    name = pointer.read_text().strip()
    folder = _results(root) / suite / name
    if not folder.is_dir():
        raise Refused(f'the {suite} baseline names run "{name}", which does not exist; promote a run again')
    return _load(folder)


def _write(path, doc):
    path.write_text(json.dumps(doc, indent=2) + '\n')


# ---------------------------------------------------------------- running

def _attempt(suite, case, folder, n):
    folder.mkdir(parents=True)
    started = time.monotonic()
    error = None
    try:
        trial = dict(suite.run_trial(case, folder) or {})
    except Exception as exc:  # a timeout or CLI error is an ERRORED trial, not a crash
        trial, error = {}, f'{type(exc).__name__}: {exc}'
    record = {'checks': None, 'cost_usd': None, 'duration_ms': None, **trial}
    if record['duration_ms'] is None:
        record['duration_ms'] = int((time.monotonic() - started) * 1000)
    record.update(n=n, state='errored' if error else suite.state(trial), error=error,
                  folder=f'{case["id"]}/t{n}', retried=False)
    return record


def _trial(suite, case, case_dir, n):
    record = _attempt(suite, case, case_dir / f't{n}', n)
    if record['state'] == 'errored':
        (case_dir / f't{n}').rename(case_dir / f't{n}-attempt1')
        record = _attempt(suite, case, case_dir / f't{n}', n)
        record['retried'] = True
    (case_dir / f't{n}' / 'trial.json').write_text(json.dumps(record, indent=2, default=str) + '\n')
    print(f'  {case["id"]} t{n}: {record["state"]}', file=sys.stderr, flush=True)
    return record


def _start(suite, root, now):
    root = Path(root)
    commit = _git(root, 'rev-parse', '--short=7', 'HEAD')
    if commit.returncode:
        raise Refused('cannot read the harness commit: the repository has no commit')
    name = run_name(now, commit.stdout.strip())
    run_dir = _results(root) / suite.name / name
    if _git(root, 'check-ignore', '-q', str(run_dir.relative_to(root))).returncode:
        raise Refused(f'the results folder {RESULTS}/ is not ignored by git. Add it to .gitignore. Nothing was written.')
    if run_dir.exists():
        raise Refused(f'the run folder {run_dir.relative_to(root)} exists; wait a second and start again')
    base = _baseline_doc(root, suite.name)
    run_dir.mkdir(parents=True)
    dirty = bool(_git(root, 'status', '--porcelain', '--', 'claude').stdout.strip())
    return run_dir, name, commit.stdout.strip(), dirty, base


def run(suite, cases, trials=DEFAULT_TRIALS, jobs=1, root=ROOT, now=None, selection=None):
    """Run every case `trials` times, write the run folder, print the report. Returns the exit code.
    `selection` names a subset for the `Eval:` line, such as `--tag ship`."""
    now = now or datetime.now()
    try:
        run_dir, name, commit, dirty, base = _start(suite, root, now)
    except Refused as why:
        print(why, file=sys.stderr)
        return 2
    began = time.monotonic()
    for case in cases:
        (run_dir / case['id']).mkdir()
    jobs_list = [(case, n) for case in cases for n in range(1, trials + 1)]
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        records = list(pool.map(lambda job: _trial(suite, job[0], run_dir / job[0]['id'], job[1]), jobs_list))
    entries = []
    for case in cases:
        own = [r for r, (c, _) in zip(records, jobs_list) if c is case]
        entries.append({'id': case['id'], 'split': case.get('split'), 'tags': case.get('tags', []),
                        'semantic_review': 'pending', 'result': case_result(suite.kind, case['id'], own),
                        'trials': own})
    costs = [r['cost_usd'] for r in records if r['cost_usd'] is not None]
    hashes = getattr(suite, 'instruction_hashes', None)
    doc = {'schema': 1, 'suite': suite.name, 'run': name, 'item_kind': suite.kind, 'harness_commit': commit,
           'dirty': dirty, 'instruction_hashes': hashes(cases) if hashes else None,
           'model': getattr(suite, 'model', None), 'trials': trials,
           'started': now.isoformat(timespec='seconds'), 'duration_ms': int((time.monotonic() - began) * 1000),
           'cost_usd': round(sum(costs), 6) if costs else None,
           'trials_without_cost': len(records) - len(costs), 'cases': entries}
    _write(run_dir / 'results.json', doc)
    shown = str(run_dir.relative_to(Path(root)))
    if base is None:
        text, code = render_report(doc, shown, selection=selection), 0
    else:
        diff = compare(base, doc)
        word, why = verdict(diff, getattr(suite, 'any_loss_is_worse', False))
        text = render_report(doc, shown, base, diff, word, why, selection)
        code = 2 if diff['unscored'] else 0 if word in ('BETTER', 'SAME') else 1
    (run_dir / 'report.md').write_text(text + '\n')
    print(text)
    return code


# ---------------------------------------------------------------- commands

def baseline(suite, case_ids, run=None, root=ROOT):
    """Promote a run to the suite's baseline. `case_ids` is every case of the suite today."""
    try:
        folders = _runs(root, suite)
        if not folders:
            raise Refused(f'there is no run of {suite} to promote')
        folder = next((f for f in folders if f.name == run), None) if run else folders[-1]
        if folder is None:
            raise Refused(f'there is no {suite} run named {run}')
        doc = _load(folder)
        missing = sorted(set(case_ids) - {c['id'] for c in doc['cases']})
        if missing:
            raise Refused(f'{folder.name} is refused: not every case ran (missing: {", ".join(missing)})')
        if doc['trials'] < DEFAULT_TRIALS:
            raise Refused(f'{folder.name} is refused: fewer trials than the default {DEFAULT_TRIALS} ({doc["trials"]})')
        errored = [t['folder'] for c in doc['cases'] for t in c['trials'] if t['state'] == 'errored']
        if errored:
            raise Refused(f'{folder.name} is refused: an ERRORED trial after retry ({", ".join(errored)})')
    except Refused as why:
        print(why, file=sys.stderr)
        return 2
    (_results(root) / suite / 'BASELINE').write_text(folder.name + '\n')
    shown = str(folder.relative_to(Path(root)))
    (folder / 'report.md').write_text(render_report(doc, shown, is_baseline=True) + '\n')
    print(f'{suite} baseline is now {folder.name}')
    return 0


def _find_run(root, run):
    path = Path(run)
    if path.is_dir():
        return path
    found = sorted(_results(root).glob(f'*/{run}'))
    if not found:
        raise Refused(f'there is no run named {run}')
    return found[0]


def review(run, case, verdict_word, note, root=ROOT, today=None):
    """Record a semantic review of one case in a run's results.json. The verdict never reads it."""
    try:
        if verdict_word not in ('ok', 'bad'):
            raise Refused('a semantic review is ok or bad')
        folder = _find_run(root, run)
        doc = _load(folder)
        entry = next((c for c in doc['cases'] if c['id'] == case), None)
        if entry is None:
            raise Refused(f'{folder.name} has no case {case}')
    except Refused as why:
        print(why, file=sys.stderr)
        return 2
    entry['semantic_review'] = {'verdict': verdict_word, 'note': note, 'date': f'{today or datetime.now():%Y-%m-%d}'}
    _write(folder / 'results.json', doc)
    print(f'{case} in {folder.name}: semantic review {verdict_word}')
    return 0


def report(root=ROOT, suite=None):
    """Print the last run's report again. Runs nothing."""
    saved = sorted((p for p in _results(root).glob(f'{suite or "*"}/*/report.md')), key=lambda p: (p.parent.name, p.parent.parent.name))
    if not saved:
        print('there is no run to report', file=sys.stderr)
        return 2
    print(saved[-1].read_text().rstrip('\n'))
    return 0
