#!/usr/bin/env python3
"""Fixture tests for review-sarif.py: one SARIF file per ticket (ADR 0145).
Round counting per approach, closing rounds left out of the count, the newest
round's findings, resolutions by round, and merging old per-round files."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / 'claude' / 'skills' / 'code-review-and-quality'
          / 'scripts' / 'review-sarif.py')
spec = importlib.util.spec_from_file_location('rs', SCRIPT)
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def round_file(path, *ids, driver='code-reviewer'):
    path.write_text(json.dumps({'version': '2.1.0', 'runs': [{
        'tool': {'driver': {'name': driver}},
        'results': [{'ruleId': i, 'message': {'text': f'{i} text'},
                     'properties': {'disposition': 'REQUIRED', 'resolution': 'open'}} for i in ids]}]}))
    return str(path)


class ReviewSarif(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = rs.main(['--dir', str(self.dir), *argv])
        return code, out.getvalue()

    def add(self, *ids, commit='aaaaaaa', extra=()):
        return self.run_cmd('add', 'AB-1', round_file(self.dir / 'r.json', *ids), '--commit', commit, *extra)

    def test_first_round_is_one(self):
        self.assertEqual(self.run_cmd('round', 'AB-1')[1].strip(), 'approach=1 round=1 counted=1')

    def test_rounds_count_up_and_closing_is_not_counted(self):
        self.add('CODE-1')
        self.add('CODE-2', commit='bbbbbbb')
        self.add(commit='ccccccc', extra=('--closing',))
        self.assertEqual(self.run_cmd('round', 'AB-1')[1].strip(), 'approach=1 round=4 counted=3')
        data = json.loads((self.dir / 'AB-1.sarif').read_text())
        self.assertEqual([r['properties']['round'] for r in data['runs']], [1, 2, 3])
        self.assertTrue(data['runs'][2]['properties']['closing'])
        self.assertEqual(data['runs'][0]['automationDetails']['id'], 'review/AB-1/a1r1/code-reviewer')

    def test_new_approach_resets_the_count_but_keeps_history(self):
        self.add('CODE-1')
        self.add('CODE-2', commit='bbbbbbb')
        self.add('CODE-1', commit='ccccccc', extra=('--new-approach',))
        self.assertEqual(self.run_cmd('round', 'AB-1')[1].strip(), 'approach=2 round=2 counted=2')
        self.assertEqual(len(json.loads((self.dir / 'AB-1.sarif').read_text())['runs']), 3)

    def test_latest_shows_only_the_newest_round(self):
        self.add('CODE-1')
        self.add('CODE-2', commit='bbbbbbb')
        out = self.run_cmd('latest', 'AB-1')[1]
        self.assertIn('round=2', out)
        self.assertIn('CODE-2', out)
        self.assertNotIn('CODE-1', out)

    def test_latest_prints_full_text_and_any_round(self):
        long = 'x' * 300
        p = self.dir / 'r.json'
        p.write_text(json.dumps({'runs': [{'tool': {'driver': {'name': 'code-reviewer'}},
                                           'results': [{'ruleId': 'CODE-1', 'message': {'text': long}}]}]}))
        self.run_cmd('add', 'AB-1', str(p), '--commit', 'aaaaaaa')
        self.add('CODE-2', commit='bbbbbbb')
        self.assertIn(long, self.run_cmd('latest', 'AB-1', '--round', '1')[1])
        everything = self.run_cmd('latest', 'AB-1', '--all', '--open')[1]
        self.assertIn('CODE-1', everything)
        self.assertIn('CODE-2', everything)

    def test_resolve_hits_the_newest_round_with_that_id(self):
        self.add('CODE-1')
        self.add('CODE-1', commit='bbbbbbb')
        self.run_cmd('resolve', 'AB-1', 'CODE-1=fixed')
        runs = json.loads((self.dir / 'AB-1.sarif').read_text())['runs']
        self.assertEqual(runs[0]['results'][0]['properties']['resolution'], 'open')
        self.assertEqual(runs[1]['results'][0]['properties']['resolution'], 'fixed')
        self.run_cmd('resolve', 'AB-1', 'CODE-1=refuted', '--round', '1')
        runs = json.loads((self.dir / 'AB-1.sarif').read_text())['runs']
        self.assertEqual(runs[0]['results'][0]['properties']['resolution'], 'refuted')

    def test_resolve_rejects_an_unknown_resolution(self):
        self.add('CODE-1')
        with self.assertRaises(SystemExit):
            self.run_cmd('resolve', 'AB-1', 'CODE-1=maybe')

    def test_old_files_block_every_command_until_merged(self):
        round_file(self.dir / 'AB-1-1111111.sarif', 'CODE-1')
        round_file(self.dir / 'AB-1-2222222.sarif', 'CODE-2')
        with self.assertRaises(SystemExit):
            self.run_cmd('round', 'AB-1')
        self.run_cmd('merge', 'AB-1')
        self.assertFalse(list(self.dir.glob('AB-1-*.sarif')))
        self.assertEqual(self.run_cmd('round', 'AB-1')[1].strip(), 'approach=1 round=3 counted=3')

    def test_other_tickets_old_files_do_not_block(self):
        round_file(self.dir / 'AB-12-1111111.sarif', 'CODE-1')
        self.assertEqual(self.run_cmd('round', 'AB-1')[0], 0)


if __name__ == '__main__':
    unittest.main()
