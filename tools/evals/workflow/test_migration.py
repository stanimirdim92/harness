"""The gate cases are folders, and two stored sets pin them.

`replay/<case>.json` pins the checks. It is a list of
`{source, output, reads, fixture, expected}`. `output` is a structured output
of the stage. `reads` is the file names the read audit counted. `fixture` is
the case whose fixture the checks run in. `expected` is the name-to-bool map
that the first, code-based checks gave on that output. The commit id of the
fixture's HEAD is written `{spec_sha}` in an output, because the id belongs to
the fixture build. `fill` puts the id back before the checks run.

`source` is `measured` (an output of the T001 run), `test_runner` (an output
that `test_runner.py` fed the checks) or `hand` (an output made from one of
those by a single edit, to give a check the value it lacked).

`fixture_manifest.json` pins the fixtures. For each case it holds the file
hashes, the commits, the git status and the evidence hash of the tree that the
first, code-based builder made. Every commit in a build has one fixed date, so
the commit ids are the same on every build.

Both sets guard the migration, so they guard the `MIGRATED` cases. A case that
is not in `MIGRATED` needs no replay file and no manifest entry. A case that
has one is checked like a migrated case.
"""
import contextlib
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import cases as casefolders
import run

HERE = Path(__file__).resolve().parent
REPLAY = HERE / 'replay'
MANIFEST = HERE / 'fixture_manifest.json'
SOURCES = ('measured', 'test_runner', 'hand')
FIXED_DATE = '2026-01-01T00:00:00+0000'
ENTRY_KEYS = {'source', 'output', 'reads', 'fixture', 'expected'}
RUNNER_CHECKS = ('fixture_unchanged', 'tool_access_confined_to_fixture')
MIGRATED = frozenset({
    'build_independent',
    'build_pressure_fan_out',
    'build_shared_db',
    'executor_fix_trailer',
    'executorsteps_done_status',
    'fix_blocked',
    'fix_next_stage',
    'fix_other_review_file',
    'fix_rerun',
    'fixround_unverified',
    'fixround_verified',
    'gate_setup_failure',
    'gate_spec_pin',
    'jira_complete',
    'jira_paginated',
    'jira_unavailable',
    'owner_accepts_required',
    'owner_approves_read_spec',
    'owner_go_over_blocker',
    'owner_preapproves_spec',
    'owner_skips_test_depth',
    'plan_conflict_incomplete',
    'plan_conflict_infeasible',
    'plan_editorial',
    'plan_handoff',
    'plan_preserved_req',
    'plan_stale',
    'plansteps_external_tracker',
    'review_auth_diff',
    'review_plain_diff',
    'review_pressure_skip_test',
    'reviewend_fix_round',
    'route_browser_check',
    'ship_answered_required',
    'ship_base_check_failed',
    'ship_open_blocker',
    'ship_open_required',
    'ship_preexisting_blocker',
    'ship_stats_order',
    'shipgate_full_run',
    'shipgate_full_run_added_tests',
    'shipgate_no_full_run',
    'spec_conflict',
    'spec_decisions',
    'spec_simple',
    'specgate_default_dec',
    'specgate_figma_read',
    'specgate_intake_blocker',
    'specgate_intake_incomplete',
    'specgate_rerun_after_brief',
    'specgate_ticket_beats_precedent',
    'testfix_packet',
    'testfull_packet',
    'testgate_figma',
    'testgate_handed_on',
    'testgate_two_candidates',
    'testresult_defect',
    'verifier_survivors',
    'verifiersteps_method_packet',
    'verifiersteps_plain_packet',
})


def current_checks(case, output, reads, directory):
    """The checks under test: the case folder's declared rules and its check.py."""
    got = casefolders.evaluate(CASES[case], output, set(reads), directory,
                               before=casefolders.snapshot(directory), confined=True)
    return {name: value for name, value in got.items() if name not in RUNNER_CHECKS}


def load_replay(folder=REPLAY):
    return {path.stem: json.loads(path.read_text()) for path in sorted(folder.glob('*.json'))}


def fill(output, sha):
    return {key: value.replace('{spec_sha}', sha) for key, value in output.items()}


def uncovered(entries):
    """Return `[(check, value)]` for each check that has no output giving `value`."""
    seen = {}
    for entry in entries:
        for name, value in entry['expected'].items():
            seen.setdefault(name, set()).add(value)
    return sorted((name, value) for name, values in seen.items() for value in (True, False) if value not in values)


def head(directory):
    if not (directory / '.git').exists():
        return ''
    return subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()


@contextlib.contextmanager
def fixed_dates():
    """Give every commit made inside the block the same date, so a fixture build gives the same commit ids."""
    keys = ('GIT_AUTHOR_DATE', 'GIT_COMMITTER_DATE')
    saved = {key: os.environ.get(key) for key in keys}
    os.environ.update({key: FIXED_DATE for key in keys})
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def tree_manifest(directory, evidence):
    """What a fixture build made: file hashes, the commits, the git status, and the evidence text."""
    directory = Path(directory)
    files = {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(directory.rglob('*'))
             if path.is_file() and '.git' not in path.relative_to(directory).parts}
    commits, status = [], []
    if (directory / '.git').exists():
        log = subprocess.check_output(['git', '-C', str(directory), 'log', '--reverse', '--format=%H %s'], text=True)
        commits = log.splitlines()
        porcelain = subprocess.check_output(['git', '-C', str(directory), 'status', '--porcelain', '-uall'], text=True)
        status = sorted(porcelain.splitlines())
    return {'files': files, 'commits': commits, 'status': status,
            'evidence': hashlib.sha256(evidence.replace(str(directory), '{directory}').encode()).hexdigest()}


def differences(got, want):
    """Name the parts of two manifests that differ."""
    out = []
    for key in ('commits', 'status', 'evidence'):
        if got[key] != want[key]:
            out.append(key)
    for path in sorted(set(got['files']) | set(want['files'])):
        if got['files'].get(path) != want['files'].get(path):
            out.append(f'file {path}')
    return out


def migration_gaps(migrated, cases, replay, manifest):
    """Name what leaves a migrated case unguarded, from the sets of case ids. A case outside `migrated` is no gap."""
    gaps = [f'{case}: migrated case has no case folder' for case in sorted(migrated - cases)]
    gaps += [f'{case}: migrated case has no replay file' for case in sorted(migrated - replay)]
    gaps += [f'{case}: migrated case has no manifest entry' for case in sorted(migrated - manifest)]
    gaps += [f'{case}: replay file has no case folder' for case in sorted(replay - cases)]
    gaps += [f'{case}: manifest entry has no case folder' for case in sorted(manifest - cases)]
    return gaps


def build_from_folder(case):
    with tempfile.TemporaryDirectory() as tmp, fixed_dates():
        directory = Path(tmp)
        evidence = casefolders.build_fixture(CASES[case], directory)
        return tree_manifest(directory, evidence)


CASES = casefolders.load_cases()


def write_manifest():
    """Rebuild `fixture_manifest.json` from the folders. Run it only for a deliberate fixture change, then review the diff."""
    MANIFEST.write_text(json.dumps({case: build_from_folder(case) for case in CASES}, indent=1, sort_keys=True) + '\n')


class ReplayShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.replay = load_replay()

    def test_every_migrated_case_keeps_its_replay_file_and_manifest_entry(self):
        stored = json.loads(MANIFEST.read_text())
        self.assertEqual(migration_gaps(MIGRATED, set(CASES), set(self.replay), set(stored)), [])

    def test_every_entry_has_the_agreed_shape(self):
        for case, entries in self.replay.items():
            self.assertTrue(entries, case)
            for n, entry in enumerate(entries):
                where = f'{case}[{n}]'
                self.assertEqual(set(entry), ENTRY_KEYS, where)
                self.assertIn(entry['source'], SOURCES, where)
                self.assertEqual(entry['fixture'], case, where)
                self.assertEqual(sorted(entry['output']), sorted(run.SCHEMA['required']), where)
                self.assertTrue(all(isinstance(v, str) for v in entry['output'].values()), where)
                self.assertTrue(all(isinstance(v, bool) for v in entry['expected'].values()), where)
                self.assertEqual(entry['reads'], sorted(entry['reads']), where)

    def test_every_case_keeps_a_measured_output(self):
        for case, entries in self.replay.items():
            self.assertIn('measured', [e['source'] for e in entries], case)

    def test_every_output_of_a_case_names_the_same_checks(self):
        for case, entries in self.replay.items():
            self.assertEqual(len({tuple(sorted(e['expected'])) for e in entries}), 1, case)

    def test_the_replay_files_hold_no_private_data(self):
        private = re.compile(r'LD-[0-9]|leadbuster')
        for path in REPLAY.glob('*.json'):
            self.assertIsNone(private.search(path.read_text()), path.name)

    def test_every_case_declares_the_two_runner_checks(self):
        for case, doc in CASES.items():
            self.assertEqual(doc['checks']['fixture_unchanged'], {'fixture_unchanged': True}, case)
            self.assertEqual(doc['checks']['tool_access_confined_to_fixture'], {'access_confined': True}, case)


class CoverageTests(unittest.TestCase):
    def test_every_check_of_every_case_has_a_true_and_a_false_output(self):
        missing = [f'{case}: {name} has no {value} output'
                   for case, entries in load_replay().items() for name, value in uncovered(entries)]
        self.assertEqual(missing, [])

    def test_a_check_with_only_true_outputs_is_reported_by_name(self):
        entries = [{'expected': {'verifies_now': True, 'figma_verifier_dispatched': True}},
                   {'expected': {'verifies_now': False, 'figma_verifier_dispatched': True}}]
        self.assertEqual(uncovered(entries), [('figma_verifier_dispatched', False)])

    def test_a_check_with_only_false_outputs_is_reported_by_name(self):
        entries = [{'expected': {'a': False}}, {'expected': {'a': False}}]
        self.assertEqual(uncovered(entries), [('a', True)])


class ReplayTests(unittest.TestCase):
    def test_every_output_gives_its_expected_checks(self):
        for case, entries in load_replay().items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                casefolders.build_fixture(CASES[case], directory)
                sha = head(directory)
                for n, entry in enumerate(entries):
                    got = current_checks(case, fill(entry['output'], sha), entry['reads'], directory)
                    differing = sorted(name for name in set(got) | set(entry['expected']) if got.get(name) != entry['expected'].get(name))
                    self.assertEqual(differing, [], f'{case}[{n}] ({entry["source"]}): checks differ from expected')


class FixtureParityTests(unittest.TestCase):
    def test_every_listed_folder_builds_the_tree_the_first_builder_made(self):
        stored = json.loads(MANIFEST.read_text())
        for case in sorted(set(stored) & set(CASES)):
            with self.subTest(case=case):
                self.assertEqual(differences(build_from_folder(case), stored[case]), [], f'{case}: the folder builds a different fixture')

    def test_the_manifest_names_the_parts_that_differ(self):
        want = {'files': {'a': '1', 'b': '2'}, 'commits': ['x m'], 'status': [], 'evidence': 'e'}
        got = {'files': {'a': '1', 'b': '3', 'c': '4'}, 'commits': ['y m'], 'status': [], 'evidence': 'e'}
        self.assertEqual(differences(got, want), ['commits', 'file b', 'file c'])


class MigrationGapTests(unittest.TestCase):
    migrated = {'a', 'b'}

    def test_a_new_case_with_no_replay_file_and_no_manifest_entry_is_no_gap(self):
        self.assertEqual(migration_gaps(self.migrated, {'a', 'b', 'new'}, {'a', 'b'}, {'a', 'b'}), [])

    def test_a_migrated_case_whose_replay_file_is_missing_is_named(self):
        self.assertEqual(migration_gaps(self.migrated, {'a', 'b'}, {'a'}, {'a', 'b'}), ['b: migrated case has no replay file'])

    def test_a_migrated_case_whose_manifest_entry_is_missing_is_named(self):
        self.assertEqual(migration_gaps(self.migrated, {'a', 'b'}, {'a', 'b'}, {'a'}), ['b: migrated case has no manifest entry'])

    def test_a_migrated_case_whose_folder_is_missing_is_named(self):
        self.assertEqual(migration_gaps(self.migrated, {'a'}, {'a', 'b'}, {'a', 'b'}),
                         ['b: migrated case has no case folder', 'b: replay file has no case folder', 'b: manifest entry has no case folder'])

    def test_a_replay_file_or_manifest_entry_of_no_case_is_named(self):
        self.assertEqual(migration_gaps(self.migrated, {'a', 'b'}, {'a', 'b', 'old'}, {'a', 'b', 'gone'}),
                         ['old: replay file has no case folder', 'gone: manifest entry has no case folder'])


if __name__ == '__main__':
    unittest.main()
