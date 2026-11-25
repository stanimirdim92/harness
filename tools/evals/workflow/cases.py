"""Gate cases as folders.

A case is `cases/<id>/` with:

    case.json   stage, request, split, tags, checks; optional setup, evidence
    files/      optional tree that the `copy` setup step puts in the fixture
    check.py    optional `def checks(result, reads, directory) -> {name: bool}`

`setup` is an ordered list of steps. With no `setup`, a case that has a
`files/` tree copies it and does nothing else.

    {"step": "copy"}                          copy files/ into the fixture, as it is
    {"step": "write", "path": P, "text": T}   write a file; "from": F reads T from a file in the case folder
    {"step": "git_init"}                      git init on branch main
    {"step": "commit", "message": M}          git add . and git commit
    {"step": "stage"}                         git add . and no commit
    {"step": "capture", "name": N}            keep the id of HEAD as N; "short": true keeps the abbreviated id

`{name}` in written text and in `evidence` becomes the value captured as
`name`. `{directory}` is the path of the fixture. Other brace text stays as
written. A placeholder whose capture comes later in the setup is an error.

`checks` maps each check name to one rule. A rule holds one of these keys,
with the keys it needs:

    {"state": V}                                     the result state equals V
    {"regex": R, "field": F}                         the field matches R
    {"not_regex": R, "field": F}                     the field does not match R
    {"decision": N, "field": F, "verdicts": [...], "equals": V}
                                                     the `N: <verdict>` line (parse_decisions) equals V
    {"report_name": V, "field": F}                   the report name (report_name) equals V
    {"status_line": A, "field": F, "equals": V}      the `A status:` line (status_line) equals V
    {"fixture_unchanged": true}                      the fixture tree is as it was before the run
    {"access_confined": true}                        the read audit stayed in the fixture

`field` is a key of the structured output, or a list of keys that are
searched as one text, joined by newlines. Regexes take inline flags, such as
`(?im)`.
"""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

from run import SCHEMA, STAGES, git, parse_decisions, report_name, status_line

CASES = Path(__file__).resolve().parent / 'cases'
FIELDS = tuple(SCHEMA['properties'])
REQUIRED = ('stage', 'request', 'split', 'tags', 'checks')
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
RULES = {
    'state': set(),
    'regex': {'field'},
    'not_regex': {'field'},
    'decision': {'field', 'verdicts', 'equals'},
    'report_name': {'field'},
    'status_line': {'field', 'equals'},
    'fixture_unchanged': set(),
    'access_confined': set(),
}
OPTIONAL = {'write': {'text', 'from'}, 'capture': {'short'}}
STEPS = {
    'copy': set(),
    'write': {'path'},
    'git_init': set(),
    'stage': set(),
    'commit': {'message'},
    'capture': {'name'},
}


class CaseError(ValueError):
    """A case folder is malformed, or a case cannot run as written."""


def load_cases(root=CASES):
    return {folder.name: load_case(folder) for folder in sorted(Path(root).iterdir()) if folder.is_dir()}


def load_case(folder):
    folder = Path(folder)
    case_id = folder.name
    path = folder / 'case.json'
    if not path.is_file():
        raise CaseError(f'case {case_id}: no case.json')
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CaseError(f'case {case_id}: case.json is not valid JSON: {exc}') from exc
    if not isinstance(doc, dict):
        raise CaseError(f'case {case_id}: case.json must hold an object')
    for field in REQUIRED:
        if field not in doc:
            raise CaseError(f'case {case_id}: missing field {field!r}')
    unknown = set(doc) - set(REQUIRED) - {'setup', 'evidence'}
    if unknown:
        raise CaseError(f'case {case_id}: unknown field {sorted(unknown)[0]!r}')
    for field in ('request', 'split'):
        if not isinstance(doc[field], str) or not doc[field]:
            raise CaseError(f'case {case_id}: field {field!r} must be a non-empty string')
    if doc['stage'] not in STAGES:
        raise CaseError(f'case {case_id}: stage {doc["stage"]!r} is not a stage of the stage map')
    if not isinstance(doc['tags'], list) or not all(isinstance(t, str) for t in doc['tags']):
        raise CaseError(f'case {case_id}: field \'tags\' must be a list of strings')
    evidence = doc.get('evidence', '')
    if not isinstance(evidence, str):
        raise CaseError(f'case {case_id}: field \'evidence\' must be a string')
    case = dict(doc, id=case_id, folder=folder, evidence=evidence, check=load_check_py(folder, case_id))
    case['setup'] = load_setup(folder, case_id, doc.get('setup'))
    declared = doc['checks']
    if not isinstance(declared, dict):
        raise CaseError(f'case {case_id}: field \'checks\' must be an object')
    if not declared and not case['check']:
        raise CaseError(f'case {case_id}: field \'checks\' declares no check and there is no check.py')
    for name, rule in declared.items():
        check_rule(case_id, name, rule)
    return case


def load_check_py(folder, case_id):
    path = folder / 'check.py'
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f'gate_case_{case_id}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, 'checks', None)):
        raise CaseError(f'case {case_id}: check.py has no checks(result, reads, directory) function')
    return module.checks


def load_setup(folder, case_id, setup):
    if setup is None:
        return [{'step': 'copy'}] if (folder / 'files').is_dir() else []
    if not isinstance(setup, list):
        raise CaseError(f'case {case_id}: field \'setup\' must be a list of steps')
    captured = set()
    started = False
    for n, step in enumerate(setup, 1):
        where = f'case {case_id}: setup step {n}'
        if not isinstance(step, dict) or step.get('step') not in STEPS:
            raise CaseError(f'{where}: step must be one of {sorted(STEPS)}, got {step!r}')
        kind = step['step']
        extra = set(step) - {'step'} - STEPS[kind] - OPTIONAL.get(kind, set())
        if extra:
            raise CaseError(f'{where}: {kind} does not take {sorted(extra)[0]!r}')
        for key in STEPS[kind]:
            if not isinstance(step.get(key), str) or not step[key]:
                raise CaseError(f'{where}: {kind} needs a non-empty {key!r}')
        if kind == 'write':
            target = Path(step['path'])
            if target.is_absolute() or '..' in target.parts:
                raise CaseError(f'{where}: write path {step["path"]!r} must stay inside the fixture')
            if ('text' in step) == ('from' in step):
                raise CaseError(f'{where}: write needs exactly one of \'text\' and \'from\'')
            source = step.get('from')
            if source is not None and not (folder / source).is_file():
                raise CaseError(f'{where}: write from {source!r}, which is not in the case folder')
            if 'text' in step and not isinstance(step['text'], str):
                raise CaseError(f'{where}: write \'text\' must be a string')
        if kind == 'git_init':
            started = True
        if kind in ('commit', 'stage', 'capture') and not started:
            raise CaseError(f'{where}: {kind} comes before git_init')
        if kind == 'capture':
            if step['name'] == 'directory':
                raise CaseError(f'{where}: \'directory\' is the fixture path and cannot be captured')
            if not isinstance(step.get('short', False), bool):
                raise CaseError(f'{where}: capture \'short\' must be true or false')
            if not NAME.match(step['name']):
                raise CaseError(f'{where}: capture name {step["name"]!r} must be a plain identifier')
            if step['name'] in captured:
                raise CaseError(f'{where}: {step["name"]!r} is captured twice')
            captured.add(step['name'])
    return setup


def check_rule(case_id, name, rule):
    where = f'case {case_id}: check {name}'
    if not isinstance(rule, dict):
        raise CaseError(f'{where}: a rule must be an object')
    kinds = [key for key in rule if key in RULES]
    if len(kinds) != 1:
        raise CaseError(f'{where}: a rule holds exactly one of {sorted(RULES)}, got {sorted(rule)}')
    kind = kinds[0]
    missing = RULES[kind] - set(rule)
    if missing:
        raise CaseError(f'{where}: {kind} needs {sorted(missing)[0]!r}')
    extra = set(rule) - {kind} - RULES[kind]
    if extra:
        raise CaseError(f'{where}: {kind} does not take {sorted(extra)[0]!r}')
    if 'field' in rule:
        for field in fields_of(rule):
            if field not in FIELDS:
                raise CaseError(f'{where}: field {field!r} is not a key of the structured output')
    if kind in ('regex', 'not_regex'):
        try:
            re.compile(rule[kind])
        except (re.error, TypeError) as exc:
            raise CaseError(f'{where}: bad regex: {exc}') from exc
    if kind == 'decision':
        verdicts = rule['verdicts']
        if not isinstance(verdicts, list) or not verdicts or not all(isinstance(v, str) and v for v in verdicts):
            raise CaseError(f'{where}: verdicts must be a non-empty list of strings')
        if rule['equals'] not in verdicts:
            raise CaseError(f'{where}: equals {rule["equals"]!r} is not one of the verdicts')
    if kind == 'status_line' and not re.fullmatch(r'[A-Za-z]+', str(rule['status_line'])):
        raise CaseError(f'{where}: status_line must name an artifact, such as "Plan"')
    if kind == 'state' and not isinstance(rule['state'], str):
        raise CaseError(f'{where}: state must be a string')


def fields_of(rule):
    field = rule['field']
    return field if isinstance(field, list) else [field]


def snapshot(directory):
    directory = Path(directory)
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file()}


def build_fixture(case, directory):
    """Run the setup steps in `directory`, which exists. Return the evidence text."""
    directory = Path(directory)
    case_id = case['id']
    later = {s['name'] for s in case['setup'] if s['step'] == 'capture'}
    captured = {'directory': str(directory)}

    def fill(text, where):
        for name in later - set(captured):
            if '{' + name + '}' in text:
                raise CaseError(f'case {case_id}: {where}: {{{name}}} is used before it is captured')
        for name, value in captured.items():
            text = text.replace('{' + name + '}', value)
        return text

    for n, step in enumerate(case['setup'], 1):
        where = f'setup step {n}'
        kind = step['step']
        try:
            if kind == 'copy':
                source = case['folder'] / 'files'
                if not source.is_dir():
                    raise CaseError(f'case {case_id}: {where}: copy needs a files/ folder')
                shutil.copytree(source, directory, dirs_exist_ok=True)
            elif kind == 'write':
                text = step['text'] if 'text' in step else (case['folder'] / step['from']).read_text()
                target = directory / step['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(fill(text, where))
            elif kind == 'git_init':
                git(directory, 'init', '-q', '-b', 'main')
            elif kind == 'stage':
                git(directory, 'add', '.')
            elif kind == 'commit':
                git(directory, 'add', '.')
                git(directory, 'commit', '-qm', step['message'])
            else:
                short = ['--short'] if step.get('short') else []
                captured[step['name']] = git(directory, 'rev-parse', *short, 'HEAD', capture=True)
        except subprocess.CalledProcessError as exc:
            raise CaseError(f'case {case_id}: {where}: {kind} failed, git exited {exc.returncode}') from exc
    return fill(case['evidence'], 'evidence')


def evaluate(case, result, reads, directory, before=None, confined=None):
    """Return `{check name: bool}`: the declared checks, then those of check.py.

    `before` is `snapshot(directory)` taken before the model ran. `confined` is
    the verdict of `run.audit_reads`."""
    case_id = case['id']
    got = {}
    for name, rule in case['checks'].items():
        got[name] = apply_rule(case_id, name, rule, result, directory, before, confined)
    if case['check']:
        custom = case['check'](result, reads, Path(directory))
        if not isinstance(custom, dict) or not all(isinstance(k, str) and isinstance(v, bool) for k, v in custom.items()):
            raise CaseError(f'case {case_id}: check.py must return a {{name: bool}} map')
        repeated = sorted(set(custom) & set(got))
        if repeated:
            raise CaseError(f'case {case_id}: check.py repeats the declared check {repeated[0]!r}')
        got.update(custom)
    return got


def apply_rule(case_id, name, rule, result, directory, before, confined):
    kind = next(key for key in rule if key in RULES)
    if kind == 'state':
        return result['state'] == rule['state']
    if kind == 'fixture_unchanged':
        if before is None:
            raise CaseError(f'case {case_id}: check {name}: fixture_unchanged needs the snapshot taken before the run')
        return snapshot(directory) == before
    if kind == 'access_confined':
        if confined is None:
            raise CaseError(f'case {case_id}: check {name}: access_confined needs the confined verdict of the read audit')
        return bool(confined)
    text = '\n'.join(result.get(field, '') for field in fields_of(rule))
    if kind == 'regex':
        return bool(re.search(rule['regex'], text))
    if kind == 'not_regex':
        return not re.search(rule['not_regex'], text)
    if kind == 'report_name':
        return report_name(text) == rule['report_name']
    if kind == 'status_line':
        return status_line(text, rule['status_line']) == rule['equals'].lower()
    verdicts = sorted(rule['verdicts'], key=len, reverse=True)
    return parse_decisions(text, [rule['decision']], verdicts).get(rule['decision'].lower()) == rule['equals'].lower()
