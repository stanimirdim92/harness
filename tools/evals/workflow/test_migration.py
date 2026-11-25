"""The replay set pins every gate check, true and false.

`replay/<case>.json` is a list of `{source, output, reads, fixture, expected}`.
`output` is a structured output of the stage. `reads` is the file names the
read audit counted. `fixture` is the case whose fixture the checks run in.
`expected` is the name-to-bool map the checks gave when the set was made.

The commit id of the fixture's HEAD is written `{spec_sha}` in an output,
because every fixture build makes a new commit id. `fill` puts the real id
back before the checks run.

`source` is `measured` (an output of the T001 run), `test_runner` (an output
that `test_runner.py` already feeds the checks) or `hand` (an output made from
one of those by a single edit, to give a check the value it lacked).
"""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import run

REPLAY = Path(__file__).resolve().parent / 'replay'
SOURCES = ('measured', 'test_runner', 'hand')
ENTRY_KEYS = {'source', 'output', 'reads', 'fixture', 'expected'}


def current_checks(case, output, reads, directory):
    """The checks under test. They are the only line that changes when the case folders replace the old code."""
    return run.checks(case, output, set(reads), directory)


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


class ReplayShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.replay = load_replay()

    def test_there_is_one_replay_file_per_case(self):
        self.assertEqual(sorted(self.replay), sorted(run.cases()))

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
                run.prepare(directory, case)
                sha = head(directory)
                for n, entry in enumerate(entries):
                    got = current_checks(case, fill(entry['output'], sha), entry['reads'], directory)
                    differing = sorted(name for name in set(got) | set(entry['expected']) if got.get(name) != entry['expected'].get(name))
                    self.assertEqual(differing, [], f'{case}[{n}] ({entry["source"]}): checks differ from expected')


if __name__ == '__main__':
    unittest.main()
