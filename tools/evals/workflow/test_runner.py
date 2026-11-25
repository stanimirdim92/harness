import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.append(str(Path(__file__).resolve().parent.parent))

import cases as casefolders
import core
import eval as eval_cli
from run import HARNESS, MUTANTS, GatesSuite, audit_reads, parse_decisions
from run import main as run_main


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        (self.directory / 'sources').mkdir()
        self.file = self.directory / 'sources/WF-1.json'
        self.file.write_text('{\n"key": "WF-1"\n}')

    def events(self, content, error=False, path='sources/WF-1.json'):
        return [
            {'message': {'content': [{'type': 'tool_use', 'id': 'read1', 'name': 'Read', 'input': {'file_path': path}}]}},
            {'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'read1', 'content': content, 'is_error': error}]}},
        ]

    def test_relative_successful_complete_read_counts(self):
        names, confined = audit_reads(self.events('1\t{\n2\t"key": "WF-1"\n3\t}'), self.directory)
        self.assertEqual(names, {'WF-1.json'})
        self.assertTrue(confined)

    def test_failed_or_truncated_read_does_not_count(self):
        for events in [self.events('Access denied', True), self.events('1\t{')]:
            self.assertEqual(audit_reads(events, self.directory)[0], set())

    def test_same_basename_outside_fixture_does_not_count(self):
        names, confined = audit_reads(self.events(self.file.read_text(), path='/unrelated/WF-1.json'), self.directory)
        self.assertFalse(names)
        self.assertFalse(confined)

    def test_glob_escape_is_detected(self):
        events = [{'message': {'content': [{'type': 'tool_use', 'id': 'glob1', 'name': 'Glob', 'input': {'pattern': '../../*'}}]}}]
        self.assertFalse(audit_reads(events, self.directory)[1])


def result(**fields):
    base = dict(state='decided', explanation='', intake='', spec='', plan='', todo='', dispatch='', reviewers='')
    base.update(fields)
    return base


class DecisionParsingTests(unittest.TestCase):
    def test_parse_decisions_prefers_longer_verdict_and_tolerates_markup(self):
        block = '- `code-reviewer`: dispatched — always\n* security-auditor: not dispatched — no trust boundary\ndistributed-systems-reviewer: Not Dispatched — none'
        parsed = parse_decisions(block, ('code-reviewer', 'security-auditor', 'distributed-systems-reviewer'), ('not dispatched', 'dispatched'))
        self.assertEqual(parsed, {'code-reviewer': 'dispatched', 'security-auditor': 'not dispatched', 'distributed-systems-reviewer': 'not dispatched'})


class VerifierFixtureTests(unittest.TestCase):
    def test_verifier_fixture_mutants_behave_as_the_evidence_says(self):
        # The evidence states which mutants stay green. Run each one, so the
        # fixture cannot claim a result the code does not give.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            evidence = casefolders.build_fixture(casefolders.load_cases()['verifier_survivors'], directory)
            source = (directory / 'pricing.py').read_text()

            def verify_passes():
                return subprocess.run(['python3', 'verify.py'], cwd=tmp, capture_output=True).returncode == 0

            self.assertTrue(verify_passes())
            for mutant, old, new, green in MUTANTS:
                self.assertEqual(source.count(old), 1, mutant)
                (directory / 'pricing.py').write_text(source.replace(old, new))
                self.assertEqual(verify_passes(), green, mutant)
                self.assertIn(f'{mutant} pricing.py: `{old}` became `{new}`. `python3 verify.py` {"passed" if green else "failed"}', evidence)
            # The boundary assertion kills M1; no clamp() input tells M2 apart.
            (directory / 'verify.py').write_text((directory / 'verify.py').read_text() + 'assert discount(100, True) == 10\n')
            (directory / 'pricing.py').write_text(source.replace('total >= 100', 'total > 100', 1))
            self.assertFalse(verify_passes())


class MainTests(unittest.TestCase):
    """`main()` runs the cases from their folders. A stand-in replaces the `claude` call."""

    def run_main(self, answer, touch=None):
        real = subprocess.run

        def fake(command, **kwargs):
            if command[0] != 'claude':
                return real(command, **kwargs)
            if touch:
                (Path(kwargs['cwd']) / touch).write_text('changed')
            event = {'type': 'result', 'is_error': False, 'structured_output': answer, 'duration_ms': 1, 'modelUsage': {}}
            kwargs['stdout'].write(json.dumps(event) + '\n')
            return subprocess.CompletedProcess(command, 0)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / 'out'
        with mock.patch.object(sys, 'argv', ['run.py', '--case', 'route_browser_check', '--output', str(out)]), \
                mock.patch.object(subprocess, 'run', fake), mock.patch('builtins.print'):
            with self.assertRaises(SystemExit) as caught:
                run_main()
        return caught.exception.code, json.loads((out / 'route_browser_check/result.json').read_text())

    def test_a_case_runs_from_its_folder_and_records_every_declared_check(self):
        code, report = self.run_main(result(dispatch='CODE-3: verifier — serves the app itself\nNext step: /test'))
        self.assertEqual(code, 0)
        self.assertEqual(report['checks'], {'check_goes_to_the_verifier': True, 'next_step_is_test': True,
                                            'fixture_unchanged': True, 'tool_access_confined_to_fixture': True})

    def test_a_wrong_answer_fails_the_case(self):
        code, report = self.run_main(result(dispatch='CODE-3: owner — no running app\nNext step: /test'))
        self.assertEqual(code, 1)
        self.assertFalse(report['checks']['check_goes_to_the_verifier'])

    def test_a_change_to_the_fixture_fails_the_case(self):
        code, report = self.run_main(result(dispatch='CODE-3: verifier — serves the app itself\nNext step: /test'), touch='stray.txt')
        self.assertEqual(code, 1)
        self.assertFalse(report['checks']['fixture_unchanged'])
        self.assertTrue(report['checks']['check_goes_to_the_verifier'])


class StubClaude:
    """Stands in for the `claude` call and passes every other command through.

    `answer(case, n, attempt)` is the structured output for one call, or None
    when `claude` prints no result event. `case` and `n` come from the trial
    folder the call runs in."""

    def __init__(self, answer, pause=0.0):
        self.answer = answer
        self.pause = pause
        self.real = subprocess.run
        self.lock = threading.Lock()
        self.running = 0
        self.peak = 0
        self.seen = {}
        self.fixtures = []

    def __call__(self, command, **kwargs):
        if command[0] != 'claude':
            return self.real(command, **kwargs)
        fixture = Path(kwargs['cwd'])
        case, n = fixture.parent.parent.name, int(fixture.parent.name[1:].split('-')[0])
        with self.lock:
            self.fixtures.append(fixture)
            self.seen[(case, n)] = attempt = self.seen.get((case, n), 0) + 1
            self.running += 1
            self.peak = max(self.peak, self.running)
        time.sleep(self.pause)
        with self.lock:
            self.running -= 1
        output = self.answer(case, n, attempt)
        if output is not None:
            event = {'type': 'result', 'is_error': False, 'structured_output': output, 'duration_ms': 7,
                     'total_cost_usd': 0.25, 'modelUsage': {'stub': {}}}
            kwargs['stdout'].write(json.dumps(event) + '\n')
        return subprocess.CompletedProcess(command, 0)


class GatesRunTests(unittest.TestCase):
    """`GatesSuite` through the core, with a stubbed `claude`: 3 cases of 3 trials."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        for args in (('init', '-q'), ('commit', '-q', '--allow-empty', '-m', 'base')):
            subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args], check=True)
        (self.root / '.gitignore').write_text('tools/evals/results/\n')
        self.cases = casefolders.load_cases(self.make_cases())
        self.suite = GatesSuite()

    def make_cases(self):
        root = Path(self.tmp.name) / 'cases'
        for case_id in ('a_pass', 'b_flaky', 'c_fail'):
            make_case(root, case_id, tags=[case_id[0]])
        return root

    @staticmethod
    def answer(case, n, attempt):
        decided = {'a_pass': True, 'b_flaky': n != 2, 'c_fail': False}[case]
        return result(state='decided' if decided else 'blocked')

    def run_gates(self, stub, jobs=4, trials=3, cases=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(subprocess, 'run', stub), redirect_stdout(out), redirect_stderr(err):
            code = core.run(self.suite, cases or list(self.cases.values()), trials=trials, jobs=jobs,
                            root=self.root, now=datetime(2026, 12, 1, 10, 0, jobs))
        runs = sorted((self.root / 'tools/evals/results/gates').iterdir())
        return code, runs[-1], json.loads((runs[-1] / 'results.json').read_text()), out.getvalue()

    def test_three_cases_of_three_trials_make_nine_separate_trial_folders(self):
        stub = StubClaude(self.answer)
        _, run, _, _ = self.run_gates(stub)
        folders = sorted(p.relative_to(run).as_posix() for p in run.glob('*/t*'))
        self.assertEqual(folders, [f'{c}/t{n}' for c in ('a_pass', 'b_flaky', 'c_fail') for n in (1, 2, 3)])
        for folder in folders:
            for name in ('fixture', 'prompt.txt', 'trace.jsonl', 'trial.json'):
                self.assertTrue((run / folder / name).exists(), f'{folder}/{name}')
        self.assertEqual(len({str(f) for f in stub.fixtures}), 9)

    def test_a_trial_builds_its_fixture_inside_its_own_folder(self):
        case = make_case(Path(self.tmp.name) / 'own', 'own', files={'AGENTS.md': 'rules\n'})
        stub = StubClaude(lambda *_: result())
        _, run, _, _ = self.run_gates(stub, trials=2, cases=[casefolders.load_case(case)])
        for n in (1, 2):
            self.assertEqual((run / f'own/t{n}/fixture/AGENTS.md').read_text(), 'rules\n')

    def test_jobs_run_trials_at_the_same_time_and_one_job_does_not(self):
        parallel = StubClaude(self.answer, pause=0.1)
        self.run_gates(parallel, jobs=4)
        serial = StubClaude(self.answer, pause=0.01)
        self.run_gates(serial, jobs=1)
        self.assertGreater(parallel.peak, 1)
        self.assertLessEqual(parallel.peak, 4)
        self.assertEqual(serial.peak, 1)

    def test_jobs_do_not_change_the_structure_of_the_results(self):
        shapes = []
        for jobs in (1, 4):
            _, _, doc, _ = self.run_gates(StubClaude(self.answer), jobs=jobs)
            shapes.append([(c['id'], c['result'], [(t['n'], t['state'], t['checks'], t['folder']) for t in c['trials']])
                           for c in doc['cases']])
        self.assertEqual(shapes[0], shapes[1])

    def test_a_case_is_pass_flaky_or_fail_from_its_trials(self):
        _, _, doc, _ = self.run_gates(StubClaude(self.answer))
        states = {c['id']: (c['result']['state'], c['result']['passed'], c['result']['scored']) for c in doc['cases']}
        self.assertEqual(states, {'a_pass': ('PASS', 3, 3), 'b_flaky': ('FLAKY', 2, 3), 'c_fail': ('FAIL', 0, 3)})
        self.assertEqual([t['state'] for t in doc['cases'][1]['trials']], ['pass', 'fail', 'pass'])

    def test_a_trial_keeps_its_checks_and_the_cost_the_cli_reports(self):
        _, _, doc, _ = self.run_gates(StubClaude(self.answer), trials=1)
        trial = doc['cases'][0]['trials'][0]
        self.assertEqual(trial['checks'], {'is_decided': True})
        self.assertEqual((trial['cost_usd'], trial['duration_ms']), (0.25, 7))
        self.assertEqual(doc['cost_usd'], 0.75)
        self.assertEqual(doc['trials_without_cost'], 0)

    def test_the_model_answer_is_kept_under_its_own_name(self):
        _, _, doc, _ = self.run_gates(StubClaude(self.answer), trials=1)
        by_case = {c['id']: c['trials'][0] for c in doc['cases']}
        self.assertEqual(by_case['a_pass']['answer_state'], 'decided')
        self.assertEqual(by_case['c_fail']['answer_state'], 'blocked')

    def test_a_trial_without_a_result_event_is_retried_and_the_first_attempt_is_kept(self):
        stub = StubClaude(lambda case, n, attempt: None if attempt == 1 else result())
        _, run, doc, _ = self.run_gates(stub, trials=1, cases=[self.cases['a_pass']])
        trial = doc['cases'][0]['trials'][0]
        self.assertEqual((trial['state'], trial['retried']), ('pass', True))
        self.assertTrue((run / 'a_pass/t1-attempt1').is_dir())

    def test_an_empty_structured_output_is_errored_after_the_retry(self):
        stub = StubClaude(lambda *_: {})
        _, run, doc, text = self.run_gates(stub, trials=1, cases=[self.cases['a_pass']])
        trial = doc['cases'][0]['trials'][0]
        self.assertEqual((trial['state'], trial['retried']), ('errored', True))
        self.assertEqual(stub.seen[('a_pass', 1)], 2)
        self.assertIsNone(doc['cases'][0]['result']['state'])
        self.assertIn('ERRORED after retry', text)

    def test_a_check_that_cannot_run_is_errored_not_failed(self):
        make_case(Path(self.tmp.name) / 'broken', 'broken', checks={'c': {'fixture_unchanged': True}},
                  setup=[{'step': 'write', 'path': 'a.txt', 'text': 'a'}])
        case = casefolders.load_case(Path(self.tmp.name) / 'broken' / 'broken')
        with mock.patch.object(casefolders, 'snapshot', return_value=None):
            stub = StubClaude(lambda *_: result())
            _, _, doc, _ = self.run_gates(stub, trials=1, cases=[case])
        trial = doc['cases'][0]['trials'][0]
        self.assertEqual(trial['state'], 'errored')
        self.assertIn('fixture_unchanged', trial['error'])

    def test_a_change_to_the_fixture_fails_the_trial_not_the_run(self):
        case = casefolders.load_case(make_case(Path(self.tmp.name) / 'edit', 'edit', checks={'u': {'fixture_unchanged': True}},
                                               files={'a.txt': 'a'}))

        def edit(case_id, n, attempt):
            (stub.fixtures[-1] / 'a.txt').write_text('changed')
            return result()

        stub = StubClaude(edit)
        _, _, doc, _ = self.run_gates(stub, trials=1, jobs=1, cases=[case])
        self.assertEqual(doc['cases'][0]['trials'][0]['checks'], {'u': False})
        self.assertEqual(doc['cases'][0]['result']['state'], 'FAIL')

    def test_the_run_records_the_hash_of_each_instruction_file_the_cases_read(self):
        _, _, doc, _ = self.run_gates(StubClaude(self.answer), trials=1)
        hashes = doc['instruction_hashes']
        self.assertEqual(sorted(hashes), sorted(['commands/ship.md', 'references/target-selection.md',
                                                  'references/findings.md', 'references/risk-tiers.md']))
        for rel, digest in hashes.items():
            self.assertEqual(digest, hashlib.sha256((HARNESS / rel).read_bytes()).hexdigest())


class GatesSuiteTests(unittest.TestCase):
    def setUp(self):
        self.suite = GatesSuite()

    def test_the_suite_follows_the_core_contract_for_gates(self):
        self.assertEqual((self.suite.name, self.suite.kind, self.suite.any_loss_is_worse), ('gates', 'case', True))

    def test_every_check_true_is_a_pass_and_any_false_is_a_fail(self):
        self.assertEqual(self.suite.state({'checks': {'a': True, 'b': True}}), 'pass')
        self.assertEqual(self.suite.state({'checks': {'a': True, 'b': False}}), 'fail')
        self.assertEqual(self.suite.state({'checks': {'a': False, 'b': False}}), 'fail')

    def test_no_checks_is_errored(self):
        for trial in ({}, {'checks': None}, {'checks': {}}):
            self.assertEqual(self.suite.state(trial), 'errored', trial)

    def test_all_cases_lists_the_case_folders_with_their_split_and_tags(self):
        listed = {c['id']: c for c in self.suite.all_cases()}
        self.assertEqual(len(listed), 60)
        self.assertEqual((listed['ship_open_blocker']['split'], listed['ship_open_blocker']['tags']), ('optimization', ['shipverdict']))


class GatesCommandTests(unittest.TestCase):
    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = eval_cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_the_gates_suite_is_built_in_the_registry(self):
        suite = eval_cli.build(eval_cli.SUITES, 'gates')
        self.assertEqual(suite.name, 'gates')

    def test_an_unknown_case_exits_2_and_names_it(self):
        code, _, err = self.cli('gates', '--case', 'nope')
        self.assertEqual(code, 2)
        self.assertIn('unknown case: nope', err)

    def test_split_optimization_keeps_every_gate_case_and_holdout_keeps_none(self):
        cases = eval_cli.build(eval_cli.SUITES, 'gates').all_cases()
        self.assertEqual(len(eval_cli.select(cases, [], [], 'optimization')), 60)
        self.assertEqual(eval_cli.select(cases, [], [], 'holdout'), [])

    def test_the_three_case_selection_of_the_real_run_resolves(self):
        cases = eval_cli.build(eval_cli.SUITES, 'gates').all_cases()
        picked = eval_cli.select(cases, ['ship_open_blocker', 'fix_rerun', 'testgate_figma'], [], None)
        self.assertEqual([c['id'] for c in picked], ['fix_rerun', 'ship_open_blocker', 'testgate_figma'])

    def test_split_dev_is_not_a_split_and_exits_2(self):
        code, _, err = self.cli('gates', '--split', 'dev')
        self.assertEqual(code, 2)
        self.assertIn("invalid choice: 'dev'", err)

    def test_jobs_default_to_4_for_gates(self):
        args = eval_cli.parser_for(eval_cli.SUITES).parse_args(['gates'])
        self.assertEqual(args.jobs, 4)


def make_case(root, case_id, files=None, check_py=None, templates=None, **fields):
    """Write `<root>/<case_id>/case.json` and its files, and return the folder."""
    folder = Path(root) / case_id
    folder.mkdir(parents=True)
    doc = dict(stage='shipverdict', request='Run /ship WF-40.', split='optimization', tags=['t'],
               checks={'is_decided': {'state': 'decided'}})
    doc.update(fields)
    doc = {k: v for k, v in doc.items() if v is not None}
    (folder / 'case.json').write_text(json.dumps(doc))
    for rel, text in (files or {}).items():
        (folder / 'files' / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / 'files' / rel).write_text(text)
    for rel, text in (templates or {}).items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(text)
    if check_py:
        (folder / 'check.py').write_text(check_py)
    return folder


class CaseFolderTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'cases'
        self.root.mkdir()
        self.fixture = Path(self.tmp.name) / 'fixture'
        self.fixture.mkdir()

    def load(self, case_id='c1', **kwargs):
        shutil.rmtree(self.root / case_id, ignore_errors=True)
        return casefolders.load_case(make_case(self.root, case_id, **kwargs))

    def evaluate(self, rules, outcome=None, reads=frozenset(), before=None, confined=None, **kwargs):
        case = self.load(checks=rules, **kwargs)
        return casefolders.evaluate(case, outcome or result(), reads, self.fixture, before=before, confined=confined)


class CaseFieldTests(CaseFolderTestCase):
    def test_a_complete_case_loads(self):
        case = self.load(setup=[{'step': 'git_init'}], evidence='note')
        self.assertEqual((case['id'], case['stage'], case['split'], case['tags']), ('c1', 'shipverdict', 'optimization', ['t']))
        self.assertEqual((case['request'], case['evidence']), ('Run /ship WF-40.', 'note'))

    def test_setup_and_evidence_are_optional(self):
        case = self.load()
        self.assertEqual((case['setup'], case['evidence']), ([], ''))

    def test_a_missing_field_names_the_case_and_the_field(self):
        for field in ('stage', 'request', 'split', 'tags', 'checks'):
            with self.subTest(field=field):
                folder = make_case(self.root, f'no_{field}', **{field: None})
                with self.assertRaises(casefolders.CaseError) as caught:
                    casefolders.load_case(folder)
                self.assertIn(f'no_{field}', str(caught.exception))
                self.assertIn(field, str(caught.exception))

    def test_a_stage_outside_the_stage_map_is_refused(self):
        with self.assertRaisesRegex(casefolders.CaseError, "c1.*stage.*nonsense"):
            self.load(stage='nonsense')

    def test_a_case_with_no_checks_at_all_is_refused(self):
        with self.assertRaisesRegex(casefolders.CaseError, 'c1.*checks'):
            self.load(checks={})

    def test_a_case_with_only_a_check_py_may_declare_no_checks(self):
        case = self.load(checks={}, check_py='def checks(result, reads, directory):\n    return {"x": True}\n')
        self.assertEqual(casefolders.evaluate(case, result(), set(), self.fixture), {'x': True})

    def test_a_case_with_no_case_json_is_refused(self):
        (self.root / 'bare').mkdir()
        with self.assertRaisesRegex(casefolders.CaseError, 'bare.*case.json'):
            casefolders.load_case(self.root / 'bare')

    def test_a_declared_rule_names_the_case_and_check_when_malformed(self):
        bad = [
            ({'x': {'state': 'decided', 'regex': 'a', 'field': 'plan'}}, 'exactly one'),
            ({'x': {'bogus': 1}}, 'exactly one'),
            ({'x': {'regex': 'a'}}, 'field'),
            ({'x': {'regex': 'a', 'field': 'nope'}}, 'nope'),
            ({'x': {'regex': '(', 'field': 'plan'}}, 'regex'),
            ({'x': {'regex': 'a', 'field': 'plan', 'extra': 1}}, 'extra'),
            ({'x': {'decision': 'a', 'field': 'dispatch', 'verdicts': ['q'], 'equals': 'z'}}, 'equals'),
            ({'x': {'status_line': 'Plan; DROP', 'field': 'explanation', 'equals': 'a'}}, 'status_line'),
        ]
        for n, (rules, word) in enumerate(bad):
            with self.subTest(rules=rules):
                with self.assertRaisesRegex(casefolders.CaseError, f'rule{n}.*check x.*{word}'):
                    self.load(case_id=f'rule{n}', checks=rules)

    def test_load_cases_lists_every_folder_by_id(self):
        make_case(self.root, 'b')
        make_case(self.root, 'a')
        self.assertEqual(list(casefolders.load_cases(self.root)), ['a', 'b'])

    def test_copying_a_case_folder_and_editing_case_json_adds_a_runnable_case(self):
        first = make_case(self.root, 'ship_open_blocker', files={'AGENTS.md': 'Old text.\n'},
                          setup=[{'step': 'copy'}, {'step': 'git_init'}, {'step': 'commit', 'message': 'base'}],
                          checks={'blocked': {'state': 'blocked'}})
        second = self.root / 'ship_open_major'
        shutil.copytree(first, second)
        doc = json.loads((second / 'case.json').read_text())
        doc['checks'] = {'decided': {'state': 'decided'}}
        (second / 'case.json').write_text(json.dumps(doc))
        (second / 'files/AGENTS.md').write_text('New text.\n')
        loaded = casefolders.load_cases(self.root)
        self.assertEqual(list(loaded), ['ship_open_blocker', 'ship_open_major'])
        directory = Path(self.tmp.name) / 'copy'
        directory.mkdir()
        casefolders.build_fixture(loaded['ship_open_major'], directory)
        self.assertEqual((directory / 'AGENTS.md').read_text(), 'New text.\n')
        self.assertTrue(casefolders.evaluate(loaded['ship_open_major'], result(), set(), directory)['decided'])
        self.assertFalse(casefolders.evaluate(loaded['ship_open_blocker'], result(), set(), directory)['blocked'])


class FixtureBuildTests(CaseFolderTestCase):
    def head(self):
        return subprocess.check_output(['git', '-C', str(self.fixture), 'rev-parse', 'HEAD'], text=True).strip()

    def test_the_plan_holds_the_real_commit_id_of_the_spec_commit(self):
        case = self.load(
            files={'requirements/WF-1-SPEC.md': 'Status: Approved\n'},
            setup=[{'step': 'copy'}, {'step': 'git_init'}, {'step': 'commit', 'message': 'Spec'},
                   {'step': 'capture', 'name': 'spec_sha'},
                   {'step': 'write', 'path': 'work/WF-1-plan.md', 'text': 'Spec revision: git-commit:{spec_sha}:requirements/WF-1-SPEC.md\n'},
                   {'step': 'commit', 'message': 'Plan'}],
            evidence='The spec is at {spec_sha}.')
        evidence = casefolders.build_fixture(case, self.fixture)
        spec_commit = subprocess.check_output(['git', '-C', str(self.fixture), 'rev-parse', 'HEAD~1'], text=True).strip()
        self.assertRegex(spec_commit, r'^[0-9a-f]{40}$')
        self.assertEqual((self.fixture / 'work/WF-1-plan.md').read_text(), f'Spec revision: git-commit:{spec_commit}:requirements/WF-1-SPEC.md\n')
        self.assertEqual(evidence, f'The spec is at {spec_commit}.')
        self.assertNotEqual(spec_commit, self.head())

    def test_each_capture_keeps_the_commit_that_was_head_at_that_step(self):
        case = self.load(
            setup=[{'step': 'git_init'},
                   {'step': 'write', 'path': 'a.txt', 'text': 'a'}, {'step': 'commit', 'message': 'A'}, {'step': 'capture', 'name': 'first'},
                   {'step': 'write', 'path': 'b.txt', 'text': 'b'}, {'step': 'commit', 'message': 'B'}, {'step': 'capture', 'name': 'second'}],
            evidence='{first} {second}')
        first, second = casefolders.build_fixture(case, self.fixture).split()
        self.assertEqual(second, self.head())
        self.assertNotEqual(first, second)
        self.assertEqual(subprocess.check_output(['git', '-C', str(self.fixture), 'rev-parse', 'HEAD~1'], text=True).strip(), first)

    def test_capture_short_keeps_the_abbreviated_commit_id(self):
        case = self.load(
            setup=[{'step': 'git_init'}, {'step': 'write', 'path': 'a.txt', 'text': 'a'}, {'step': 'commit', 'message': 'A'},
                   {'step': 'capture', 'name': 'full'}, {'step': 'capture', 'name': 'short', 'short': True}],
            evidence='{full} {short}')
        full, short = casefolders.build_fixture(case, self.fixture).split()
        self.assertEqual(full, self.head())
        self.assertEqual(short, subprocess.check_output(['git', '-C', str(self.fixture), 'rev-parse', '--short', 'HEAD'], text=True).strip())
        self.assertLess(len(short), len(full))

    def test_stage_adds_the_tree_without_committing(self):
        case = self.load(
            setup=[{'step': 'git_init'}, {'step': 'write', 'path': 'a.txt', 'text': 'a'}, {'step': 'commit', 'message': 'A'},
                   {'step': 'write', 'path': 'a.txt', 'text': 'b'}, {'step': 'write', 'path': 'new.txt', 'text': 'n'}, {'step': 'stage'}])
        casefolders.build_fixture(case, self.fixture)
        status = subprocess.check_output(['git', '-C', str(self.fixture), 'status', '--porcelain'], text=True)
        self.assertEqual(status.splitlines(), ['M  a.txt', 'A  new.txt'])

    def test_the_fixture_directory_is_a_placeholder(self):
        case = self.load(setup=[{'step': 'write', 'path': 'a.txt', 'text': 'at {directory}'}], evidence='Repo root: {directory}.')
        evidence = casefolders.build_fixture(case, self.fixture)
        self.assertEqual(evidence, f'Repo root: {self.fixture}.')
        self.assertEqual((self.fixture / 'a.txt').read_text(), f'at {self.fixture}')

    def test_directory_cannot_be_captured(self):
        with self.assertRaisesRegex(casefolders.CaseError, "c1.*step 2.*'directory'"):
            self.load(setup=[{'step': 'git_init'}, {'step': 'capture', 'name': 'directory'}])

    def test_write_takes_its_text_from_a_file_in_the_case_folder(self):
        case = self.load(
            templates={'templates/plan.md': 'Pinned at {sha}\n'},
            setup=[{'step': 'git_init'}, {'step': 'write', 'path': 'a.txt', 'text': 'a'}, {'step': 'commit', 'message': 'A'},
                   {'step': 'capture', 'name': 'sha'},
                   {'step': 'write', 'path': 'work/plan.md', 'from': 'templates/plan.md'}])
        casefolders.build_fixture(case, self.fixture)
        self.assertEqual((self.fixture / 'work/plan.md').read_text(), f'Pinned at {self.head()}\n')

    def test_copy_brings_the_files_tree_and_does_not_replace_placeholders(self):
        case = self.load(files={'src/a.py': 'X = {"k": 1}\n', 'note.md': '{sha}\n'},
                         setup=[{'step': 'copy'}])
        casefolders.build_fixture(case, self.fixture)
        self.assertEqual((self.fixture / 'src/a.py').read_text(), 'X = {"k": 1}\n')
        self.assertEqual((self.fixture / 'note.md').read_text(), '{sha}\n')

    def test_a_case_with_files_and_no_setup_copies_them(self):
        case = self.load(files={'AGENTS.md': 'rules\n'})
        casefolders.build_fixture(case, self.fixture)
        self.assertEqual((self.fixture / 'AGENTS.md').read_text(), 'rules\n')

    def test_text_that_is_not_a_placeholder_stays_as_written(self):
        case = self.load(setup=[{'step': 'write', 'path': 'a.py', 'text': 'print(f"{value}")\n'}], evidence='{not_captured}')
        evidence = casefolders.build_fixture(case, self.fixture)
        self.assertEqual((self.fixture / 'a.py').read_text(), 'print(f"{value}")\n')
        self.assertEqual(evidence, '{not_captured}')

    def test_a_placeholder_used_before_its_capture_is_refused(self):
        case = self.load(setup=[{'step': 'git_init'}, {'step': 'write', 'path': 'a.txt', 'text': '{sha}'},
                                {'step': 'commit', 'message': 'A'}, {'step': 'capture', 'name': 'sha'}])
        with self.assertRaisesRegex(casefolders.CaseError, 'c1.*step 2.*sha'):
            casefolders.build_fixture(case, self.fixture)

    def test_a_commit_or_capture_before_git_init_is_refused_at_load(self):
        for n, step in enumerate(({'step': 'commit', 'message': 'A'}, {'step': 'capture', 'name': 'a'}, {'step': 'stage'})):
            with self.assertRaisesRegex(casefolders.CaseError, f'init{n}.*step 1.*git_init'):
                casefolders.load_case(make_case(self.root, f'init{n}', setup=[step]))

    def test_a_bad_setup_step_is_refused_at_load(self):
        bad = [
            ([{'step': 'explode'}], 'explode'),
            ([{'step': 'commit'}], 'message'),
            ([{'step': 'capture'}], 'name'),
            ([{'step': 'write', 'path': 'a'}], 'text'),
            ([{'step': 'write', 'path': 'a', 'text': 'x', 'from': 'y'}], 'text'),
            ([{'step': 'write', 'path': '../a', 'text': 'x'}], 'path'),
            ([{'step': 'write', 'path': '/a', 'text': 'x'}], 'path'),
            ([{'step': 'write', 'path': 'a', 'from': 'missing.md'}], 'missing.md'),
            ([{'step': 'git_init'}, {'step': 'capture', 'name': 'a'}, {'step': 'capture', 'name': 'a'}], 'twice'),
            ([{'step': 'copy', 'extra': 1}], 'extra'),
            ('copy', 'setup'),
        ]
        for n, (setup, word) in enumerate(bad):
            with self.subTest(setup=setup):
                with self.assertRaisesRegex(casefolders.CaseError, f'bad{n}.*{word}'):
                    casefolders.load_case(make_case(self.root, f'bad{n}', setup=setup))

    def test_copy_without_a_files_folder_is_refused(self):
        case = self.load(setup=[{'step': 'copy'}])
        with self.assertRaisesRegex(casefolders.CaseError, 'c1.*files'):
            casefolders.build_fixture(case, self.fixture)


class DeclaredCheckTests(CaseFolderTestCase):
    def test_state_equals_a_value(self):
        rules = {'blocked': {'state': 'blocked'}}
        self.assertEqual(self.evaluate(rules, result(state='blocked')), {'blocked': True})
        self.assertEqual(self.evaluate(rules, result(state='decided')), {'blocked': False})

    def test_regex_matches_the_named_field_only(self):
        rules = {'no_go': {'field': 'explanation', 'regex': 'NO-GO'}}
        self.assertTrue(self.evaluate(rules, result(explanation='Ship Decision: NO-GO'))['no_go'])
        self.assertFalse(self.evaluate(rules, result(explanation='GO', plan='NO-GO'))['no_go'])

    def test_regex_takes_inline_flags(self):
        rules = {'x': {'field': 'explanation', 'regex': r'(?im)^ship decision: no-go$'}}
        self.assertTrue(self.evaluate(rules, result(explanation='a\nShip Decision: NO-GO\nb'))['x'])

    def test_not_regex_is_true_only_when_the_pattern_is_absent(self):
        rules = {'quiet': {'field': 'plan', 'not_regex': r'^Handoff:'}}
        self.assertTrue(self.evaluate(rules, result(plan='# Plan'))['quiet'])
        self.assertFalse(self.evaluate({'quiet': {'field': 'plan', 'not_regex': '(?m)^Handoff:'}}, result(plan='x\nHandoff: Ready'))['quiet'])

    def test_a_list_of_fields_is_searched_as_one_text(self):
        rules = {'x': {'field': ['explanation', 'plan'], 'regex': r'one\ntwo'}}
        self.assertTrue(self.evaluate(rules, result(explanation='one', plan='two'))['x'])
        self.assertFalse(self.evaluate(rules, result(explanation='one', todo='two'))['x'])

    def test_decision_line_equals_a_value(self):
        rule = {'decision': 'ws-report', 'field': 'dispatch', 'verdicts': ['concurrent', 'queued'], 'equals': 'queued'}
        self.assertTrue(self.evaluate({'x': rule}, result(dispatch='ws-label: concurrent — a\n- `ws-report`: Queued — b'))['x'])
        self.assertFalse(self.evaluate({'x': rule}, result(dispatch='ws-report: concurrent — a'))['x'])
        self.assertFalse(self.evaluate({'x': rule}, result(dispatch='ws-label: queued — a'))['x'])

    def test_decision_prefers_the_longer_verdict_whatever_the_declared_order(self):
        rule = {'decision': 'ws-report', 'field': 'dispatch', 'verdicts': ['queued', 'queued late'], 'equals': 'queued late'}
        self.assertTrue(self.evaluate({'x': rule}, result(dispatch='ws-report: queued late — a'))['x'])
        rule = dict(rule, equals='queued')
        self.assertFalse(self.evaluate({'x': rule}, result(dispatch='ws-report: queued late — a'))['x'])

    def test_decision_does_not_read_not_dispatched_as_dispatched(self):
        rule = {'decision': 'security-auditor', 'field': 'reviewers', 'verdicts': ['dispatched', 'not dispatched'], 'equals': 'dispatched'}
        self.assertFalse(self.evaluate({'x': rule}, result(reviewers='security-auditor: not dispatched — none'))['x'])
        self.assertTrue(self.evaluate({'x': rule}, result(reviewers='security-auditor: dispatched — none'))['x'])

    def test_report_name_reads_the_first_line_only(self):
        rule = {'report_name': 'BUILD BLOCKED', 'field': 'explanation'}
        self.assertTrue(self.evaluate({'x': rule}, result(explanation='**BUILD BLOCKED**\n- CODE-1'))['x'])
        self.assertFalse(self.evaluate({'x': rule}, result(explanation='Report.\nBUILD BLOCKED'))['x'])
        self.assertFalse(self.evaluate({'x': rule}, result(explanation='BUILD COMPLETE'))['x'])

    def test_status_line_equals_a_value(self):
        rule = {'status_line': 'Plan', 'field': 'explanation', 'equals': 'Needs reapproval'}
        self.assertTrue(self.evaluate({'x': rule}, result(explanation='BUILD BLOCKED\n`Plan status`: needs reapproval.\nSpec status: unchanged'))['x'])
        self.assertFalse(self.evaluate({'x': rule}, result(explanation='Spec status: needs reapproval'))['x'])

    def test_fixture_unchanged_compares_the_tree_with_the_snapshot_before_the_run(self):
        (self.fixture / 'a.txt').write_text('a')
        before = casefolders.snapshot(self.fixture)
        rules = {'untouched': {'fixture_unchanged': True}}
        self.assertTrue(self.evaluate(rules, before=before)['untouched'])
        (self.fixture / 'a.txt').write_text('changed')
        self.assertFalse(self.evaluate(rules, before=before)['untouched'])
        (self.fixture / 'a.txt').write_text('a')
        (self.fixture / 'new.txt').write_text('n')
        self.assertFalse(self.evaluate(rules, before=before)['untouched'])

    def test_fixture_unchanged_without_a_snapshot_is_an_error(self):
        with self.assertRaisesRegex(casefolders.CaseError, 'fixture_unchanged.*before'):
            self.evaluate({'untouched': {'fixture_unchanged': True}})

    def test_access_confined_reports_the_audit_verdict(self):
        rules = {'confined': {'access_confined': True}}
        self.assertTrue(self.evaluate(rules, confined=True)['confined'])
        self.assertFalse(self.evaluate(rules, confined=False)['confined'])

    def test_access_confined_without_the_audit_verdict_is_an_error(self):
        with self.assertRaisesRegex(casefolders.CaseError, 'access_confined.*confined'):
            self.evaluate({'confined': {'access_confined': True}})


class CustomCheckTests(CaseFolderTestCase):
    CHECK_PY = ('def checks(result, reads, directory):\n'
                '    return {"survivors_named": "M3" in result["dispatch"], "reads_ok": "a.json" in reads,\n'
                '            "dir_ok": (directory / "marker").exists()}\n')

    def test_custom_checks_run_beside_the_declared_ones(self):
        (self.fixture / 'marker').write_text('m')
        got = self.evaluate({'is_decided': {'state': 'decided'}}, result(dispatch='M3: survived'), reads={'a.json'}, check_py=self.CHECK_PY)
        self.assertEqual(got, {'is_decided': True, 'survivors_named': True, 'reads_ok': True, 'dir_ok': True})

    def test_a_failing_custom_check_shows_false(self):
        got = self.evaluate({'is_decided': {'state': 'decided'}}, result(dispatch='M1: killed'), check_py=self.CHECK_PY)
        self.assertFalse(got['survivors_named'])
        self.assertTrue(got['is_decided'])

    def test_a_custom_name_that_repeats_a_declared_name_is_refused(self):
        with self.assertRaisesRegex(casefolders.CaseError, 'c1.*is_decided'):
            self.evaluate({'is_decided': {'state': 'decided'}}, check_py='def checks(result, reads, directory):\n    return {"is_decided": True}\n')

    def test_a_custom_return_that_is_not_a_name_to_bool_map_is_refused(self):
        for n, body in enumerate(('return [True]', 'return {"a": 1}', 'return {1: True}')):
            with self.subTest(body=body):
                folder = make_case(self.root, f'ret{n}', check_py=f'def checks(result, reads, directory):\n    {body}\n')
                case = casefolders.load_case(folder)
                with self.assertRaisesRegex(casefolders.CaseError, f'ret{n}.*check.py'):
                    casefolders.evaluate(case, result(), set(), self.fixture)

    def test_a_check_py_without_a_checks_function_is_refused_at_load(self):
        with self.assertRaisesRegex(casefolders.CaseError, 'c1.*check.py.*checks'):
            self.load(check_py='x = 1\n')


if __name__ == '__main__':
    unittest.main()
