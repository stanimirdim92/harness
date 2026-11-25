#!/usr/bin/env python3
"""The eval core, with a fake suite and a throwaway git repository. `claude` is never invoked. Runs in CI."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

import core
import eval as eval_cli

NOW = datetime(2026, 12, 1, 10, 15, 0)


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), '-c', 'user.email=t@t', '-c', 'user.name=t', *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def make_repo(root, ignore='tools/evals/results/\n'):
    git(root, 'init', '-q')
    (root / '.gitignore').write_text(ignore)
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'base')
    return git(root, 'rev-parse', '--short=7', 'HEAD')


class FakeSuite:
    """Plays scripted outcomes: `script[(case, n)]` is a list, one entry per attempt.
    An entry is a trial dict, or an Exception to raise, or the string 'empty'."""
    kind = 'case'
    any_loss_is_worse = False
    model = 'opus'

    def __init__(self, name='gates', script=None, kind='case', hashes=None, any_loss_is_worse=False):
        self.name = name
        self.kind = kind
        self.hashes = hashes
        self.any_loss_is_worse = any_loss_is_worse
        self.script = script or {}
        self.calls = []

    def instruction_hashes(self, cases):
        return self.hashes

    def run_trial(self, case, folder):
        n = int(folder.name[1:])
        assert folder.is_dir()
        attempts = self.script.get((case['id'], n), [{'ok': True}])
        done = len([c for c in self.calls if c == (case['id'], n)])
        self.calls.append((case['id'], n))
        outcome = attempts[min(done, len(attempts) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        if outcome == 'empty':
            return {'output': ''}
        return dict(outcome)

    def state(self, trial):
        if trial.get('output') == '':
            return 'errored'
        if trial.get('checks') is not None and self.kind == 'check':
            return 'pass' if all(trial['checks'].values()) else 'fail'
        return 'pass' if trial.get('ok') else 'fail'


def case(name, split='optimization', tags=()):
    return {'id': name, 'split': split, 'tags': list(tags)}


class CoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sha = make_repo(self.root)
        self.n = 0

    def tearDown(self):
        self.tmp.cleanup()

    def tick(self):
        self.n += 1
        return datetime(2026, 12, 1, 10, 15, self.n)

    def run_core(self, suite, cases, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        kwargs.setdefault('now', self.tick())
        with redirect_stdout(out), redirect_stderr(err):
            code = core.run(suite, cases, root=self.root, **kwargs)
        return code, out.getvalue(), err.getvalue()

    def runs(self, suite='gates'):
        base = self.root / 'tools/evals/results' / suite
        return sorted(p for p in base.iterdir() if p.is_dir()) if base.exists() else []

    def doc(self, run):
        return json.loads((run / 'results.json').read_text())

    def promote(self, suite, names, run=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = core.baseline(suite, names, run=run, root=self.root)
        return code, out.getvalue(), err.getvalue()


class RunFolder(CoreCase):
    def test_run_is_stored_under_timestamp_and_harness_commit(self):
        code, _, _ = self.run_core(FakeSuite(), [case('a')], now=NOW)
        self.assertEqual(code, 0)
        self.assertEqual([p.name for p in self.runs()], [f'2026-12-01-101500-{self.sha}'])

    def test_unignored_results_folder_stops_before_writing_anything(self):
        (self.root / '.gitignore').write_text('')
        code, _, err = self.run_core(FakeSuite(), [case('a')])
        self.assertEqual(code, 2)
        self.assertIn('not ignored', err)
        self.assertFalse((self.root / 'tools/evals/results').exists())

    def test_second_run_in_the_same_second_stops_and_keeps_the_first(self):
        suite = FakeSuite()
        self.run_core(suite, [case('a')], now=NOW)
        first = (self.runs()[0] / 'results.json').read_text()
        code, _, err = self.run_core(FakeSuite(script={('a', 1): [{'ok': False}]}), [case('a')], now=NOW)
        self.assertEqual(code, 2)
        self.assertIn('exists', err)
        self.assertEqual((self.runs()[0] / 'results.json').read_text(), first)

    def test_repository_without_a_commit_stops(self):
        empty = self.root / 'empty'
        empty.mkdir()
        git(empty, 'init', '-q')
        (empty / '.gitignore').write_text('tools/evals/results/\n')
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = core.run(FakeSuite(), [case('a')], root=empty, now=NOW)
        self.assertEqual(code, 2)
        self.assertFalse((empty / 'tools/evals/results').exists())


class ResultsFile(CoreCase):
    def test_schema_1_holds_every_field_of_the_run(self):
        suite = FakeSuite(hashes={'claude/a.md': 'h1'})
        script = {('a', n): [{'ok': True, 'checks': {'c1': True}, 'cost_usd': 0.5, 'duration_ms': 100}] for n in (1, 2, 3)}
        suite.script = script
        self.run_core(suite, [case('a', 'holdout', ['ship'])], now=NOW)
        doc = self.doc(self.runs()[0])
        self.assertEqual(doc['schema'], 1)
        self.assertEqual(doc['suite'], 'gates')
        self.assertEqual(doc['harness_commit'], self.sha)
        self.assertIs(doc['dirty'], False)
        self.assertEqual(doc['instruction_hashes'], {'claude/a.md': 'h1'})
        self.assertEqual(doc['model'], 'opus')
        self.assertEqual(doc['trials'], 3)
        self.assertEqual(doc['started'], '2026-12-01T10:15:00')
        self.assertIsInstance(doc['duration_ms'], int)
        self.assertEqual(doc['cost_usd'], 1.5)
        self.assertEqual(doc['trials_without_cost'], 0)
        entry = doc['cases'][0]
        self.assertEqual((entry['id'], entry['split'], entry['tags']), ('a', 'holdout', ['ship']))
        self.assertEqual(entry['result']['state'], 'PASS')
        self.assertEqual(entry['semantic_review'], 'pending')
        trial = entry['trials'][1]
        self.assertEqual((trial['n'], trial['state'], trial['checks'], trial['cost_usd'], trial['duration_ms']),
                         (2, 'pass', {'c1': True}, 0.5, 100))
        self.assertEqual(trial['folder'], 'a/t2')

    def test_unknown_values_are_null_and_never_left_out(self):
        self.run_core(FakeSuite(), [case('a')], trials=1, now=NOW)
        doc = self.doc(self.runs()[0])
        self.assertIsNone(doc['instruction_hashes'])
        trial = doc['cases'][0]['trials'][0]
        self.assertIn('cost_usd', trial)
        self.assertIsNone(trial['cost_usd'])
        self.assertIsNone(trial['checks'])
        self.assertIsNone(doc['cost_usd'])

    def test_run_total_counts_trials_without_cost(self):
        suite = FakeSuite(script={('a', 1): [{'ok': True, 'cost_usd': 1.0}], ('a', 2): [{'ok': True}],
                                  ('a', 3): [{'ok': True, 'cost_usd': 2.0}]})
        _, out, _ = self.run_core(suite, [case('a')], now=NOW)
        doc = self.doc(self.runs()[0])
        self.assertEqual(doc['cost_usd'], 3.0)
        self.assertEqual(doc['trials_without_cost'], 1)
        self.assertIn('1 trial had no cost', out)

    def test_dirty_flag_follows_the_claude_folder(self):
        (self.root / 'claude').mkdir()
        (self.root / 'claude/x.md').write_text('x')
        self.run_core(FakeSuite(), [case('a')], trials=1, now=NOW)
        self.assertIs(self.doc(self.runs()[0])['dirty'], True)


class Trials(CoreCase):
    def test_default_is_three_trials_in_their_own_folders(self):
        self.run_core(FakeSuite(), [case('a')], now=NOW)
        run = self.runs()[0]
        self.assertEqual(sorted(p.name for p in (run / 'a').iterdir()), ['t1', 't2', 't3'])

    def test_trials_flag_raises_the_count(self):
        self.run_core(FakeSuite(), [case('a')], trials=5, now=NOW)
        self.assertEqual(len(self.doc(self.runs()[0])['cases'][0]['trials']), 5)

    def test_errored_trial_is_retried_once_and_the_retry_is_scored(self):
        suite = FakeSuite(script={('a', 2): [TimeoutError('timed out'), {'ok': True}]})
        code, out, _ = self.run_core(suite, [case('a')], now=NOW)
        trial = self.doc(self.runs()[0])['cases'][0]['trials'][1]
        self.assertEqual((trial['state'], trial['retried']), ('pass', True))
        self.assertEqual(suite.calls.count(('a', 2)), 2)
        self.assertIn('1 retry', out)

    def test_empty_output_counts_as_errored_and_is_retried(self):
        suite = FakeSuite(script={('a', 1): ['empty', {'ok': True}]})
        self.run_core(suite, [case('a')], now=NOW)
        trial = self.doc(self.runs()[0])['cases'][0]['trials'][0]
        self.assertEqual((trial['state'], trial['retried']), ('pass', True))

    def test_failed_first_attempt_is_kept_beside_the_retry(self):
        suite = FakeSuite(script={('a', 2): [TimeoutError('timed out'), {'ok': True}]})
        self.run_core(suite, [case('a')], now=NOW)
        names = sorted(p.name for p in (self.runs()[0] / 'a').iterdir())
        self.assertEqual(names, ['t1', 't2', 't2-attempt1', 't3'])

    def test_second_failure_stays_errored_and_is_not_scored(self):
        suite = FakeSuite(script={('a', 2): [TimeoutError('timed out'), TimeoutError('timed out again')]})
        code, out, _ = self.run_core(suite, [case('a')], now=NOW)
        entry = self.doc(self.runs()[0])['cases'][0]
        self.assertEqual(entry['trials'][1]['state'], 'errored')
        self.assertIn('timed out again', entry['trials'][1]['error'])
        self.assertEqual(suite.calls.count(('a', 2)), 2)
        self.assertEqual((entry['result']['scored'], entry['result']['passed'], entry['result']['state']), (2, 2, 'PASS'))
        self.assertIn('ERRORED', out)
        self.assertIn('a/t2', out)

    def test_errored_trial_is_neither_a_pass_nor_a_fail(self):
        suite = FakeSuite(script={('a', 1): [{'ok': False}], ('a', 2): ['empty'], ('a', 3): [{'ok': False}]})
        self.run_core(suite, [case('a')], now=NOW)
        result = self.doc(self.runs()[0])['cases'][0]['result']
        self.assertEqual((result['state'], result['scored'], result['passed']), ('FAIL', 2, 0))

    def test_jobs_run_the_same_structure_in_separate_folders(self):
        cases = [case('a'), case('b'), case('c')]
        self.run_core(FakeSuite(), cases, jobs=3, now=NOW)
        run = self.runs()[0]
        folders = [t['folder'] for c in self.doc(run)['cases'] for t in c['trials']]
        self.assertEqual(len(folders), 9)
        self.assertEqual(len(set(folders)), 9)
        self.assertTrue(all((run / f).is_dir() for f in folders))
        self.assertEqual([c['id'] for c in self.doc(run)['cases']], ['a', 'b', 'c'])


class CaseState(unittest.TestCase):
    def trials(self, *states):
        return [{'n': i + 1, 'state': s, 'checks': None} for i, s in enumerate(states)]

    def test_pass_when_every_scored_trial_passed(self):
        self.assertEqual(core.case_result('case', 'a', self.trials('pass', 'pass', 'errored'))['state'], 'PASS')

    def test_flaky_when_some_passed(self):
        result = core.case_result('case', 'a', self.trials('pass', 'fail', 'pass'))
        self.assertEqual((result['state'], result['passed'], result['scored']), ('FLAKY', 2, 3))

    def test_fail_when_none_passed(self):
        self.assertEqual(core.case_result('case', 'a', self.trials('fail', 'fail', 'errored'))['state'], 'FAIL')

    def test_no_state_when_every_trial_errored(self):
        result = core.case_result('case', 'a', self.trials('errored', 'errored'))
        self.assertIsNone(result['state'])
        self.assertEqual(result['scored'], 0)

    def test_check_items_get_their_own_state_over_trials(self):
        trials = [{'n': 1, 'state': 'pass', 'checks': {'x': True, 'y': True, 'z': False}},
                  {'n': 2, 'state': 'fail', 'checks': {'x': True, 'y': False, 'z': False}},
                  {'n': 3, 'state': 'errored', 'checks': None}]
        result = core.case_result('check', 'add-business', trials)
        self.assertEqual(result['items'], {'x': 'PASS', 'y': 'FLAKY', 'z': 'FAIL'})
        self.assertEqual((result['passed'], result['scored']), (1, 2))

    def test_case_item_is_the_case_itself(self):
        result = core.case_result('case', 'a', self.trials('pass', 'fail'))
        self.assertEqual(result['items'], {'a': 'FLAKY'})


def make_doc(suite, items, kind='case', holdout=(), trials=3, commit='abc1234', hashes=None, started='2026-11-20T09:00:00',
             cost=1.0, duration=60000):
    """A results.json holding the given item states. For `case` items each item is its own case."""
    cases = []
    if kind == 'case':
        for name, state in items.items():
            cases.append({'id': name, 'split': 'holdout' if name in holdout else 'optimization', 'tags': [],
                          'semantic_review': 'pending',
                          'trials': [{'n': 1, 'state': 'fail', 'folder': f'{name}/t1'}],
                          'result': {'state': state, 'passed': 0, 'scored': trials, 'items': {name: state}}})
    else:
        cases.append({'id': 'add-business', 'split': 'holdout' if 'add-business' in holdout else 'optimization',
                      'tags': [], 'semantic_review': 'pending',
                      'trials': [{'n': 1, 'state': 'fail', 'folder': 'add-business/t1'}],
                      'result': {'state': 'FLAKY', 'passed': 1, 'scored': trials, 'items': dict(items)}})
    return {'schema': 1, 'suite': suite, 'item_kind': kind, 'harness_commit': commit, 'dirty': False,
            'instruction_hashes': hashes, 'model': None, 'trials': trials, 'started': started,
            'duration_ms': duration, 'cost_usd': cost, 'trials_without_cost': 0, 'cases': cases}


class Verdict(unittest.TestCase):
    def judge(self, base, run, kind='case', holdout=(), any_loss=False, suite='gates'):
        base_doc = make_doc(suite, base, kind, holdout)
        run_doc = make_doc(suite, run, kind, holdout)
        diff = core.compare(base_doc, run_doc)
        return core.verdict(diff, any_loss_is_worse=any_loss)[0], diff

    def test_gate_becomes_flaky_is_worse_even_with_two_gains(self):
        base = {'ship_open_blocker': 'PASS', 'x': 'FAIL', 'y': 'FAIL'}
        run = {'ship_open_blocker': 'FLAKY', 'x': 'PASS', 'y': 'PASS'}
        word, diff = self.judge(base, run, any_loss=True)
        self.assertEqual(word, 'WORSE')
        self.assertEqual(diff['lost'], ['ship_open_blocker'])
        self.assertEqual(diff['gained'], ['x', 'y'])

    def test_same_loss_in_a_suite_without_the_gate_rule_is_only_better(self):
        base = {'ship_open_blocker': 'PASS', 'x': 'FAIL', 'y': 'FAIL'}
        run = {'ship_open_blocker': 'FLAKY', 'x': 'PASS', 'y': 'PASS'}
        self.assertEqual(self.judge(base, run, any_loss=False, suite='bugs')[0], 'BETTER')

    def test_holdout_lost_is_worse_despite_three_gains(self):
        base = {'h': 'PASS', 'a': 'FAIL', 'b': 'FAIL', 'c': 'FAIL'}
        run = {'h': 'FAIL', 'a': 'PASS', 'b': 'PASS', 'c': 'PASS'}
        self.assertEqual(self.judge(base, run, holdout=('h',), suite='bugs')[0], 'WORSE')

    def test_holdout_that_was_flaky_in_the_baseline_does_not_trigger_the_rule(self):
        base = {'h': 'FLAKY', 'a': 'FAIL', 'b': 'FAIL'}
        run = {'h': 'FAIL', 'a': 'PASS', 'b': 'PASS'}
        self.assertEqual(self.judge(base, run, holdout=('h',), suite='bugs')[0], 'BETTER')

    def test_holdout_still_passing_is_not_lost(self):
        base = {'h': 'PASS', 'a': 'FAIL'}
        run = {'h': 'PASS', 'a': 'PASS'}
        self.assertEqual(self.judge(base, run, holdout=('h',), suite='bugs')[0], 'BETTER')

    def test_subset_run_unchanged_is_same_and_covers_only_its_items(self):
        base = {f'c{i}': 'PASS' for i in range(20)}
        run = {f'c{i}': 'PASS' for i in range(8)}
        word, diff = self.judge(base, run, any_loss=True)
        self.assertEqual(word, 'SAME')
        self.assertEqual(diff['compared'], 8)

    def test_task_check_lost_is_not_better_not_worse(self):
        base = {'AC3-dup-phone': 'PASS', 'IR-double-submit': 'FLAKY'}
        run = {'AC3-dup-phone': 'FLAKY', 'IR-double-submit': 'PASS'}
        word, diff = self.judge(base, run, kind='check', holdout=('add-business',), suite='tasks')
        self.assertEqual(word, 'NOT BETTER')
        self.assertEqual((diff['lost'], diff['gained']), (['AC3-dup-phone'], ['IR-double-submit']))

    def test_new_case_is_listed_and_not_counted(self):
        base = {'a': 'PASS'}
        run = {'a': 'PASS', 'fresh': 'FAIL'}
        word, diff = self.judge(base, run, any_loss=True)
        self.assertEqual(word, 'SAME')
        self.assertEqual(diff['new'], ['fresh'])
        self.assertEqual((diff['gained'], diff['lost']), ([], []))

    def test_more_gained_than_lost_is_better(self):
        word, _ = self.judge({'a': 'PASS', 'b': 'FAIL', 'c': 'FAIL'}, {'a': 'FLAKY', 'b': 'PASS', 'c': 'PASS'}, suite='bugs')
        self.assertEqual(word, 'BETTER')

    def test_equal_gained_and_lost_is_not_better(self):
        word, _ = self.judge({'a': 'PASS', 'b': 'FAIL'}, {'a': 'FLAKY', 'b': 'PASS'}, suite='bugs')
        self.assertEqual(word, 'NOT BETTER')

    def test_more_lost_than_gained_is_not_better(self):
        word, _ = self.judge({'a': 'PASS', 'b': 'PASS', 'c': 'FAIL'}, {'a': 'FLAKY', 'b': 'FAIL', 'c': 'FLAKY'}, suite='bugs')
        self.assertEqual(word, 'NOT BETTER')

    def test_nothing_changed_is_same(self):
        self.assertEqual(self.judge({'a': 'FLAKY'}, {'a': 'FLAKY'})[0], 'SAME')

    def test_every_step_up_counts_as_gained(self):
        _, diff = self.judge({'a': 'FAIL', 'b': 'FLAKY'}, {'a': 'FLAKY', 'b': 'PASS'})
        self.assertEqual(diff['gained'], ['a', 'b'])

    def test_unscored_item_is_set_aside_not_lost(self):
        base_doc = make_doc('gates', {'a': 'PASS'})
        run_doc = make_doc('gates', {'a': None})
        diff = core.compare(base_doc, run_doc)
        self.assertEqual((diff['lost'], diff['unscored']), ([], ['a']))


class Comparison(CoreCase):
    """A run measured against a promoted baseline, end to end."""

    def baseline_run(self, script=None, cases=None):
        cases = cases or [case('a'), case('b')]
        self.run_core(FakeSuite(script=script, hashes={'f': '1'}), cases, now=NOW)
        base = self.runs()[0].name
        self.assertEqual(self.promote('gates', [c['id'] for c in cases])[0], 0)
        return base

    def test_run_without_a_baseline_prints_no_verdict_and_how_to_promote(self):
        code, out, _ = self.run_core(FakeSuite(), [case('a')], now=NOW)
        self.assertEqual(code, 0)
        self.assertNotIn('Verdict:', out)
        self.assertIn('No baseline', out)
        self.assertIn('baseline gates', out)

    def test_exit_1_when_the_verdict_is_worse(self):
        self.baseline_run()
        suite = FakeSuite(script={('a', 1): [{'ok': False}]}, any_loss_is_worse=True, hashes={'f': '2'})
        code, out, _ = self.run_core(suite, [case('a'), case('b')])
        self.assertEqual(code, 1)
        self.assertIn('Verdict: WORSE', out)
        self.assertIn('Lost: a', out)

    def test_exit_0_when_nothing_changed_and_the_noise_line_prints(self):
        self.baseline_run()
        code, out, _ = self.run_core(FakeSuite(hashes={'f': '1'}), [case('a'), case('b')])
        self.assertEqual(code, 0)
        self.assertIn('Verdict: SAME', out)
        self.assertIn('harness unchanged since baseline: this run measures noise', out)

    def test_no_noise_line_when_a_harness_file_changed(self):
        self.baseline_run()
        _, out, _ = self.run_core(FakeSuite(hashes={'f': '2'}), [case('a'), case('b')])
        self.assertNotIn('measures noise', out)

    def test_no_noise_line_when_hashes_are_unknown(self):
        self.run_core(FakeSuite(), [case('a')], now=NOW)
        self.promote('gates', ['a'])
        _, out, _ = self.run_core(FakeSuite(), [case('a')])
        self.assertNotIn('measures noise', out)

    def test_exit_2_when_a_case_has_no_scored_trial(self):
        self.baseline_run()
        suite = FakeSuite(script={('a', n): [TimeoutError('t')] for n in (1, 2, 3)}, hashes={'f': '1'})
        code, out, _ = self.run_core(suite, [case('a'), case('b')])
        self.assertEqual(code, 2)
        self.assertIn('a/t1', out)

    def test_report_names_baseline_commit_date_cost_and_duration_beside_the_run(self):
        self.baseline_run(script={('a', 1): [{'ok': True, 'cost_usd': 2.0}]})
        suite = FakeSuite(script={('a', 1): [{'ok': True, 'cost_usd': 3.0}]}, hashes={'f': '2'})
        _, out, _ = self.run_core(suite, [case('a'), case('b')])
        self.assertIn(f'Baseline: {self.sha}, 2026-12-01', out)
        self.assertIn('$3.00 (baseline $2.00)', out)
        self.assertRegex(out, r'Duration: .* \(baseline .*\)')

    def test_read_these_names_flaky_and_changed_cases_with_their_failing_trial_folders(self):
        self.baseline_run()
        suite = FakeSuite(script={('a', 2): [{'ok': False}], ('b', 1): [{'ok': False}], ('b', 2): [{'ok': False}],
                                  ('b', 3): [{'ok': False}]}, hashes={'f': '2'})
        _, out, _ = self.run_core(suite, [case('a'), case('b')])
        read = out.split('Read these:')[1]
        self.assertIn('a/t2', read)
        self.assertNotIn('a/t1', read)
        for n in (1, 2, 3):
            self.assertIn(f'b/t{n}', read)
        self.assertIn('Flaky: a (2/3)', out)

    def test_new_case_is_listed_by_name(self):
        self.baseline_run()
        _, out, _ = self.run_core(FakeSuite(hashes={'f': '2'}), [case('a'), case('b'), case('fresh')])
        self.assertIn('New: fresh', out)
        self.assertIn('Verdict: SAME', out)

    def test_report_file_equals_the_printed_report(self):
        _, out, _ = self.run_core(FakeSuite(), [case('a')], now=NOW)
        saved = (self.runs()[0] / 'report.md').read_text()
        self.assertEqual(out.strip(), saved.strip())

    def test_report_command_prints_the_last_run_again(self):
        _, out, _ = self.run_core(FakeSuite(), [case('a')], now=NOW)
        printed = io.StringIO()
        with redirect_stdout(printed):
            code = core.report(root=self.root)
        self.assertEqual(code, 0)
        self.assertEqual(printed.getvalue().strip(), out.strip())

    def test_report_command_with_no_run_exits_2(self):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = core.report(root=self.root)
        self.assertEqual(code, 2)

    def test_task_run_lists_check_names_in_the_report(self):
        script = {('add-business', 1): [{'checks': {'AC3': True, 'IR': False}}]}
        suite = FakeSuite(name='tasks', kind='check', script=script)
        self.run_core(suite, [case('add-business')], trials=1, now=NOW)
        # trials=1 is below the default, so promote through a 3 trial run instead.
        script = {('add-business', n): [{'checks': {'AC3': True, 'IR': n == 1}}] for n in (1, 2, 3)}
        self.run_core(FakeSuite(name='tasks', kind='check', script=script), [case('add-business')])
        self.promote('tasks', ['add-business'])
        script = {('add-business', n): [{'checks': {'AC3': n != 3, 'IR': True}}] for n in (1, 2, 3)}
        code, out, _ = self.run_core(FakeSuite(name='tasks', kind='check', script=script), [case('add-business')])
        self.assertEqual(code, 1)
        self.assertIn('Verdict: NOT BETTER', out)
        self.assertIn('Lost: AC3', out)
        self.assertIn('Gained: IR', out)


class Baseline(CoreCase):
    def full_run(self, **kwargs):
        self.run_core(FakeSuite(**kwargs), [case('a'), case('b')])
        return self.runs()[-1]

    def pointer(self):
        return (self.root / 'tools/evals/results/gates/BASELINE').read_text()

    def test_promoting_a_full_run_writes_the_pointer_file(self):
        run = self.full_run()
        code, out, _ = self.promote('gates', ['a', 'b'])
        self.assertEqual(code, 0)
        self.assertEqual(self.pointer().strip(), run.name)
        self.assertEqual(len(self.pointer().strip().splitlines()), 1)

    def test_latest_run_is_the_default_and_a_named_run_is_honoured(self):
        first = self.full_run()
        second = self.full_run()
        self.promote('gates', ['a', 'b'], run=first.name)
        self.assertEqual(self.pointer().strip(), first.name)
        self.promote('gates', ['a', 'b'])
        self.assertEqual(self.pointer().strip(), second.name)

    def test_subset_is_refused_and_names_the_reason(self):
        self.run_core(FakeSuite(), [case('a')])
        code, _, err = self.promote('gates', ['a', 'b'])
        self.assertEqual(code, 2)
        self.assertIn('not every case ran', err)
        self.assertIn('b', err)
        self.assertFalse((self.root / 'tools/evals/results/gates/BASELINE').exists())

    def test_fewer_trials_than_the_default_is_refused(self):
        self.run_core(FakeSuite(), [case('a'), case('b')], trials=1)
        code, _, err = self.promote('gates', ['a', 'b'])
        self.assertEqual(code, 2)
        self.assertIn('fewer trials than the default 3', err)

    def test_more_trials_than_the_default_is_accepted(self):
        self.run_core(FakeSuite(), [case('a'), case('b')], trials=4)
        self.assertEqual(self.promote('gates', ['a', 'b'])[0], 0)

    def test_errored_trial_after_retry_is_refused(self):
        script = {('a', 2): [TimeoutError('x'), TimeoutError('x')]}
        self.run_core(FakeSuite(script=script), [case('a'), case('b')])
        code, _, err = self.promote('gates', ['a', 'b'])
        self.assertEqual(code, 2)
        self.assertIn('ERRORED', err)
        self.assertIn('a/t2', err)

    def test_retry_that_succeeded_does_not_block_promotion(self):
        script = {('a', 2): [TimeoutError('x'), {'ok': True}]}
        self.run_core(FakeSuite(script=script), [case('a'), case('b')])
        self.assertEqual(self.promote('gates', ['a', 'b'])[0], 0)

    def test_run_without_schema_1_results_is_refused(self):
        old = self.root / 'tools/evals/results/gates/2025-01-01-000000-abc1234'
        old.mkdir(parents=True)
        (old / 'results.json').write_text(json.dumps({'results': {}}))
        code, _, err = self.promote('gates', ['a'])
        self.assertEqual(code, 2)
        self.assertIn('schema 1', err)

    def test_run_folder_without_results_file_is_refused(self):
        old = self.root / 'tools/evals/results/gates/2025-01-01-000000-abc1234'
        old.mkdir(parents=True)
        code, _, err = self.promote('gates', ['a'])
        self.assertEqual(code, 2)
        self.assertIn('schema 1', err)

    def test_suite_without_runs_is_refused(self):
        code, _, err = self.promote('gates', ['a'])
        self.assertEqual(code, 2)
        self.assertIn('no run', err)

    def test_unknown_run_name_is_refused(self):
        self.full_run()
        code, _, err = self.promote('gates', ['a', 'b'], run='2020-01-01-000000-abc1234')
        self.assertEqual(code, 2)

    def test_pointer_to_a_missing_run_stops_the_next_run(self):
        self.full_run()
        self.promote('gates', ['a', 'b'])
        (self.root / 'tools/evals/results/gates/BASELINE').write_text('gone\n')
        code, _, err = self.run_core(FakeSuite(), [case('a'), case('b')])
        self.assertEqual(code, 2)
        self.assertIn('gone', err)
        self.assertEqual(len(self.runs()), 1)


class SemanticReview(CoreCase):
    def review(self, *args, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = core.review(*args, root=self.root, **kwargs)
        return code, err.getvalue()

    def test_review_records_verdict_note_and_date(self):
        self.run_core(FakeSuite(), [case('fix_rerun')], now=NOW)
        run = self.runs()[0]
        self.assertEqual(self.doc(run)['cases'][0]['semantic_review'], 'pending')
        code, _ = self.review(run.name, 'fix_rerun', 'ok', 'names CODE-1 skip', today=datetime(2026, 12, 2))
        self.assertEqual(code, 0)
        self.assertEqual(self.doc(run)['cases'][0]['semantic_review'],
                         {'verdict': 'ok', 'note': 'names CODE-1 skip', 'date': '2026-12-02'})

    def test_review_accepts_a_path_to_the_run_folder(self):
        self.run_core(FakeSuite(), [case('a')], now=NOW)
        run = self.runs()[0]
        self.assertEqual(self.review(str(run), 'a', 'bad', 'wrong')[0], 0)
        self.assertEqual(self.doc(run)['cases'][0]['semantic_review']['verdict'], 'bad')

    def test_unknown_case_unknown_run_and_bad_verdict_exit_2(self):
        self.run_core(FakeSuite(), [case('a')], now=NOW)
        run = self.runs()[0]
        self.assertEqual(self.review(run.name, 'nope', 'ok', 'n')[0], 2)
        self.assertEqual(self.review('2020-01-01-000000-abc1234', 'a', 'ok', 'n')[0], 2)
        code, err = self.review(run.name, 'a', 'maybe', 'n')
        self.assertEqual(code, 2)
        self.assertIn('ok or bad', err)
        self.assertEqual(self.doc(run)['cases'][0]['semantic_review'], 'pending')

    def test_verdict_does_not_read_the_review(self):
        self.run_core(FakeSuite(), [case('a')], now=NOW)
        self.promote('gates', ['a'])
        base = self.runs()[0]
        self.review(base.name, 'a', 'bad', 'looks wrong')
        suite = FakeSuite(script={('a', 1): [{'ok': False}]}, any_loss_is_worse=True)
        _, with_review, _ = self.run_core(suite, [case('a')])
        self.assertIn('Verdict: WORSE', with_review)
        self.review(base.name, 'a', 'ok', 'fine')
        suite = FakeSuite(script={('a', 1): [{'ok': False}]}, any_loss_is_worse=True)
        _, other, _ = self.run_core(suite, [case('a')])
        self.assertIn('Verdict: WORSE', other)

    def test_report_marks_a_pending_review(self):
        _, out, _ = self.run_core(FakeSuite(), [case('a')], now=NOW)
        self.assertRegex(out, r'semantic review pending: a')


class BuiltSuite(FakeSuite):
    """A fake suite that also lists its cases, as eval.py needs."""

    def __init__(self, cases, **kwargs):
        super().__init__(**kwargs)
        self.listed = cases

    def all_cases(self):
        return self.listed


class RecallStub:
    """A recall suite that records the arguments it was handed."""

    def __init__(self, code):
        self.code, self.argv = code, None

    def run(self, argv):
        self.argv = argv
        return self.code


CASES = [case('a', 'optimization', ['ship']), case('b', 'holdout', ['ship', 'fix']), case('c', 'optimization', ['fix'])]
README_TEXT = """# evals

## Measured

One full run of every `workflow/` case.

| Item | Value |
| --- | --- |
| Cases | 60, one trial each |
| Total cost | $15.6664 |

| Case | Cost (USD) |
| --- | --- |
| `a` | 0.9385 |

## Next
"""


class EvalEntry(CoreCase):
    """eval.py with a registry of fake suites. `claude` is never invoked."""

    def cli(self, *argv, built=('gates', 'tasks', 'bugs'), suite=None, readme=README_TEXT):
        self.suite = suite or BuiltSuite(CASES, name='gates')
        registry = {name: {'question': f'Q of {name}?', 'when': f'W of {name}', 'cost': None,
                           'build': (lambda: self.suite) if name in built else None}
                    for name in ('gates', 'tasks', 'bugs', 'recall')}
        registry['recall']['cost'] = 'free'
        readme_file = self.root / 'README.md'
        readme_file.write_text(readme)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = eval_cli.main(list(argv), suites=registry, root=self.root, readme=readme_file)
        return code, out.getvalue(), err.getvalue()

    def test_no_arguments_prints_the_four_suites_and_exits_0(self):
        code, out, _ = self.cli()
        self.assertEqual(code, 0)
        for name in ('gates', 'tasks', 'bugs', 'recall'):
            self.assertIn(f'Q of {name}?', out)
            self.assertIn(f'W of {name}', out)

    def test_cost_comes_from_the_measured_section_or_says_unmeasured(self):
        _, out, _ = self.cli()
        self.assertIn('last measured cost: $15.67 (60 cases, one trial each)', out)
        self.assertEqual(out.count('last measured cost: unmeasured'), 2)
        self.assertIn('last measured cost: free', out)

    def test_every_suite_is_unmeasured_when_the_readme_has_no_measured_section(self):
        _, out, _ = self.cli(readme='# evals\n')
        self.assertNotIn('$', out)
        self.assertEqual(out.count('unmeasured'), 3)

    def test_the_real_readme_gives_gates_a_dollar_figure(self):
        text = eval_cli.suite_table(eval_cli.SUITES, eval_cli.README.read_text())
        self.assertRegex(text, r'gates\n.*\n.*\n  last measured cost: \$\d+\.\d\d')

    def test_the_real_registry_lists_four_suites_and_gates_and_recall_are_built(self):
        self.assertEqual(list(eval_cli.SUITES), ['gates', 'tasks', 'bugs', 'recall'])
        self.assertEqual([name for name, entry in eval_cli.SUITES.items() if entry['build'] is not None],
                         ['gates', 'recall'])
        self.assertEqual(eval_cli.SUITES['recall']['cost'], 'free')

    def test_a_suite_not_built_yet_says_so_and_exits_2(self):
        for argv in (('gates',), ('baseline', 'gates'), ('recall',)):
            code, _, err = self.cli(*argv, built=())
            self.assertEqual(code, 2)
            self.assertIn('not built yet', err)
        self.assertFalse((self.root / 'tools/evals/results').exists())

    def test_case_and_tag_repeat_and_select_the_union(self):
        code, _, _ = self.cli('gates', '--case', 'c', '--tag', 'ship', '--tag', 'nothing')
        self.assertEqual(code, 0)
        self.assertEqual(sorted({c for c, _ in self.suite.calls}), ['a', 'b', 'c'])

    def test_case_alone_selects_only_that_case(self):
        self.cli('gates', '--case', 'a', '--case', 'c')
        self.assertEqual(sorted({c for c, _ in self.suite.calls}), ['a', 'c'])

    def test_tag_alone_selects_only_the_tagged_cases(self):
        self.cli('gates', '--tag', 'fix')
        self.assertEqual(sorted({c for c, _ in self.suite.calls}), ['b', 'c'])

    def test_split_keeps_only_that_split(self):
        self.cli('gates', '--split', 'holdout')
        self.assertEqual(sorted({c for c, _ in self.suite.calls}), ['b'])

    def test_split_narrows_a_tag_selection(self):
        self.cli('gates', '--tag', 'ship', '--split', 'optimization')
        self.assertEqual(sorted({c for c, _ in self.suite.calls}), ['a'])

    def test_no_flags_runs_every_case_with_the_default_three_trials(self):
        self.cli('gates')
        self.assertEqual(len(self.suite.calls), 9)

    def test_trials_and_jobs_reach_the_core(self):
        self.cli('gates', '--case', 'a', '--trials', '2', '--jobs', '2')
        self.assertEqual(self.suite.calls.count(('a', 1)) + self.suite.calls.count(('a', 2)), 2)
        self.assertNotIn(('a', 3), self.suite.calls)

    def test_jobs_value_is_handed_to_the_core(self):
        with mock.patch.object(core, 'run', return_value=0) as run:
            self.cli('gates', '--jobs', '4', '--trials', '5')
        self.assertEqual((run.call_args.kwargs['jobs'], run.call_args.kwargs['trials']), (4, 5))

    def test_tasks_and_bugs_take_the_same_flags(self):
        for name in ('tasks', 'bugs'):
            suite = BuiltSuite(CASES, name=name)
            code, _, _ = self.cli(name, '--tag', 'fix', '--split', 'holdout', '--trials', '1', '--jobs', '2', suite=suite)
            self.assertEqual(code, 0)
            self.assertEqual(sorted({c for c, _ in suite.calls}), ['b'])

    def test_unknown_case_exits_2_before_any_run(self):
        code, _, err = self.cli('gates', '--case', 'nope')
        self.assertEqual(code, 2)
        self.assertIn('nope', err)
        self.assertFalse((self.root / 'tools/evals/results').exists())

    def test_flags_that_select_nothing_exit_2(self):
        code, _, err = self.cli('gates', '--tag', 'zzz')
        self.assertEqual(code, 2)
        self.assertIn('no case matches', err)
        self.assertEqual(self.suite.calls, [])

    def test_bad_flag_values_exit_2(self):
        self.assertEqual(self.cli('gates', '--split', 'bogus')[0], 2)
        self.assertEqual(self.cli('gates', '--trials', '0')[0], 2)
        self.assertEqual(self.cli('gates', '--jobs', 'x')[0], 2)

    def test_recall_hands_every_argument_to_the_recall_suite(self):
        argv = ['--repo', 'r', '--ticket', 'LD-380', '--subject-only', '--min-recall', '0.5', '--json', '-h']
        suite = RecallStub(7)
        code, _, _ = self.cli('recall', *argv, built=('recall',), suite=suite)
        self.assertEqual((code, suite.argv), (7, argv))

    def test_recall_takes_no_run_flags_of_its_own(self):
        suite = RecallStub(0)
        self.cli('recall', '--case', 'a', '--trials', '2', built=('recall',), suite=suite)
        self.assertEqual(suite.argv, ['--case', 'a', '--trials', '2'])

    def test_recall_writes_no_run_folder(self):
        self.cli('recall', '--plan', 'p', built=('recall',), suite=RecallStub(0))
        self.assertFalse((self.root / 'tools/evals/results').exists())

    def test_baseline_refuses_a_subset_run_using_the_suites_full_case_list(self):
        suite = BuiltSuite(CASES, name='gates')
        self.run_core(suite, [CASES[0]])
        code, _, err = self.cli('baseline', 'gates', suite=suite)
        self.assertEqual(code, 2)
        self.assertIn('not every case ran', err)
        self.assertIn('b', err)

    def test_baseline_promotes_a_full_run_and_honours_a_named_run(self):
        suite = BuiltSuite(CASES, name='gates')
        self.run_core(suite, CASES)
        first = self.runs()[0].name
        self.run_core(suite, CASES[:1])
        code, out, _ = self.cli('baseline', 'gates', first, suite=suite)
        self.assertEqual(code, 0)
        self.assertEqual((self.root / 'tools/evals/results/gates/BASELINE').read_text().strip(), first)

    def test_report_reprints_the_last_run_without_running_anything(self):
        suite = BuiltSuite(CASES, name='gates')
        _, shown, _ = self.run_core(suite, CASES)
        calls = len(suite.calls)
        code, out, _ = self.cli('report', suite=suite)
        self.assertEqual((code, out.strip()), (0, shown.strip()))
        self.assertEqual(len(suite.calls), calls)

    def test_report_works_with_no_suite_built(self):
        self.run_core(BuiltSuite(CASES, name='gates'), CASES)
        self.assertEqual(self.cli('report', built=())[0], 0)

    def test_review_records_the_note_in_the_run(self):
        self.run_core(BuiltSuite(CASES, name='gates'), CASES)
        run = self.runs()[0]
        code, _, _ = self.cli('review', run.name, 'b', 'bad', 'names the wrong file', built=())
        self.assertEqual(code, 0)
        review = self.doc(run)['cases'][1]['semantic_review']
        self.assertEqual((review['verdict'], review['note']), ('bad', 'names the wrong file'))

    def test_review_needs_ok_or_bad(self):
        self.run_core(BuiltSuite(CASES, name='gates'), CASES)
        self.assertEqual(self.cli('review', self.runs()[0].name, 'a', 'maybe', 'n')[0], 2)

    def test_unknown_suite_for_baseline_exits_2(self):
        self.assertEqual(self.cli('baseline', 'nope')[0], 2)

    def test_core_exit_code_passes_through(self):
        self.run_core(BuiltSuite(CASES, name='gates'), CASES)
        self.cli('baseline', 'gates')
        suite = BuiltSuite(CASES, name='gates', any_loss_is_worse=True,
                           script={('a', 1): [{'ok': False}], ('a', 2): [{'ok': False}], ('a', 3): [{'ok': False}]})
        code, out, _ = self.cli('gates', suite=suite)
        self.assertEqual(code, 1)
        self.assertIn('Verdict: WORSE', out)


class RecallPassthrough(unittest.TestCase):
    """`eval.py recall` and `recall.py` run for real on a temp git repo. Recall reads git and the plan only."""

    EVAL = Path(eval_cli.__file__).resolve()
    RECALL = EVAL.parent / 'plan-recall' / 'recall.py'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        git(self.repo, 'init', '-q')
        (self.repo / 'a.php').write_text('a\n')
        (self.repo / 'b.php').write_text('b\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'base')
        self.base = git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'a.php').write_text('a2\n')
        (self.repo / 'b.php').write_text('b2\n')
        git(self.repo, 'commit', '-qam', 'LD-380 T001: change both')
        (self.repo / 'plan.md').write_text('**Files/areas likely touched:**\n- `a.php`\n')

    def both(self, *flags):
        args = ['--repo', str(self.repo), '--plan', 'plan.md', '--range', f'{self.base}..HEAD', *flags]
        run = lambda *command: subprocess.run([sys.executable, *command, *args], capture_output=True, text=True)
        return run(str(self.RECALL)), run(str(self.EVAL), 'recall')

    def test_same_figures_and_exit_code(self):
        direct, through = self.both('--ticket', 'LD-380', '--subject-only', '--show-commits')
        self.assertEqual((through.returncode, through.stdout), (direct.returncode, direct.stdout))
        self.assertIn('recall (existing files)  : 50%', through.stdout)
        self.assertIn('scored commits (1):', through.stdout)

    def test_the_gate_exit_code_passes_through(self):
        direct, through = self.both('--min-recall', '0.9')
        self.assertEqual((direct.returncode, through.returncode), (1, 1))
        direct, through = self.both('--min-recall', '0.5')
        self.assertEqual((direct.returncode, through.returncode), (0, 0))

    def test_json_output_is_identical(self):
        direct, through = self.both('--json')
        self.assertEqual(through.stdout, direct.stdout)
        self.assertEqual(json.loads(through.stdout)['missed'], ['b.php'])

    def test_a_bad_argument_gives_recalls_own_error_and_code(self):
        direct, through = self.both('--no-such-flag')
        self.assertEqual((through.returncode, through.stderr.split('error:')[-1]),
                         (direct.returncode, direct.stderr.split('error:')[-1]))
        self.assertEqual(through.returncode, 2)

    def test_no_run_folder_is_written(self):
        before = set((self.EVAL.parent / 'results').rglob('*')) if (self.EVAL.parent / 'results').exists() else set()
        self.both()
        after = set((self.EVAL.parent / 'results').rglob('*')) if (self.EVAL.parent / 'results').exists() else set()
        self.assertEqual(after, before)


class RunName(unittest.TestCase):
    def test_run_names_sort_by_time(self):
        self.assertRegex(core.run_name(NOW, 'abc1234'), r'^2026-12-01-101500-abc1234$')


if __name__ == '__main__':
    unittest.main()
