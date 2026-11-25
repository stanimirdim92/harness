import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cases as casefolders
from run import MUTANTS, audit_reads, parse_decisions
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


def make_case(root, case_id, files=None, check_py=None, templates=None, **fields):
    """Write `<root>/<case_id>/case.json` and its files, and return the folder."""
    folder = Path(root) / case_id
    folder.mkdir(parents=True)
    doc = dict(stage='shipverdict', request='Run /ship WF-40.', split='dev', tags=['t'],
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
        self.assertEqual((case['id'], case['stage'], case['split'], case['tags']), ('c1', 'shipverdict', 'dev', ['t']))
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
