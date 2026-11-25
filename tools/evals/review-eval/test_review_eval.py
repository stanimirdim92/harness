#!/usr/bin/env python3
"""Tests for review-eval: a case built from a real bugfix history, and judging.

History: A adds feed.py; B introduces the bug on line 3; C edits another file;
F fixes line 3. The case must name B and the line B wrote, and a finding there
must count as caught. Producing drives the model and is not tested here."""
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('re_run', HERE / 'run.py')
rev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rev)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), '-c', 'user.email=t@t', '-c', 'user.name=t', *args],
                          capture_output=True, text=True, check=True).stdout.strip()


class History(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.repo = Path(self.tmp.name)
        git(r, 'init', '-q')
        (r / 'feed.py').write_text('def order(posts):\n    posts = list(posts)\n    return posts\n')
        git(r, 'add', '-A'); git(r, 'commit', '-qm', 'A')
        (r / 'feed.py').write_text('def order(posts):\n    posts = list(posts)\n    return sorted(posts)[1:]\n')
        git(r, 'commit', '-qam', 'B'); self.bug = git(r, 'rev-parse', 'HEAD')
        (r / 'other.py').write_text('x = 1\n')
        git(r, 'add', '-A'); git(r, 'commit', '-qm', 'C')
        (r / 'feed.py').write_text('def order(posts):\n    posts = list(posts)\n    return sorted(posts)\n')
        git(r, 'commit', '-qam', 'F'); self.fix = git(r, 'rev-parse', 'HEAD')

    def tearDown(self):
        self.tmp.cleanup()

    def test_blame_finds_the_bug_and_its_line(self):
        case = rev.bug_case(self.repo, self.fix)
        self.assertEqual(case['change'], self.bug)
        self.assertEqual(case['targets'], {'feed.py': [3]})

    def test_judging(self):
        case = {**rev.bug_case(self.repo, self.fix), 'defect': ['drops the first', r'\[1:\]']}
        sarif = lambda line, disp, text='The slice drops the first post.': json.dumps(
            {'runs': [{'tool': {'driver': {'name': 'code-reviewer'}}, 'results': [
                {'ruleId': 'CODE-1', 'message': {'text': text}, 'properties': {'disposition': disp},
                 'locations': [{'physicalLocation': {'artifactLocation': {'uri': 'feed.py'},
                                                     'region': {'startLine': line}}}]}]}]})
        self.assertTrue(rev.judge(case, rev.sarif_findings(sarif(4, 'BLOCKER')))['caught'])
        far = rev.judge(case, rev.sarif_findings(sarif(40, 'BLOCKER')))
        self.assertFalse(far['caught'])
        advisory = rev.judge(case, rev.sarif_findings(sarif(3, 'ADVISORY')))
        self.assertEqual((advisory['caught'], advisory['caught_any']), (False, True))

    def test_a_nearby_finding_about_something_else_is_located_not_caught(self):
        # LD-585: every finding near the fixed lines was about another part of the change.
        case = {**rev.bug_case(self.repo, self.fix), 'defect': ['drops the first']}
        other = json.dumps({'runs': [{'results': [
            {'ruleId': 'CODE-4', 'message': {'text': 'Leading spaces are not trimmed.'},
             'properties': {'disposition': 'BLOCKER'},
             'locations': [{'physicalLocation': {'artifactLocation': {'uri': 'feed.py'}, 'region': {'startLine': 3}}}]}]}]})
        result = rev.judge(case, rev.sarif_findings(other))
        self.assertEqual((result['caught'], result['located']), (False, True))

    def test_a_case_without_defect_terms_is_never_caught(self):
        case = rev.bug_case(self.repo, self.fix)
        near = [('feed.py', 3, 'BLOCKER', 'The slice drops the first post.')]
        result = rev.judge(case, near)
        self.assertEqual((result['caught'], result['located']), (False, True))

    def test_the_markdown_fallback_keeps_the_finding_text(self):
        case = {**rev.bug_case(self.repo, self.fix), 'defect': ['drops the first']}
        report = '### BLOCKER\n- [CODE-1] [feed.py:3] (confidence: high) The slice drops the first post.\n'
        self.assertTrue(rev.judge(case, rev.markdown_findings(report))['caught'])

    def test_keep_saves_report_meta_and_sarif(self):
        with tempfile.TemporaryDirectory() as tmp:
            sarif = Path(tmp) / 'REVIEW-EVAL-abc.sarif'
            sarif.write_text('{"runs": []}')
            out = Path(tmp) / 'out' / 'case-1'
            rev.keep(out, {'result': '## Review\nNothing to fix.', 'total_cost_usd': 1.5}, [sarif])
            self.assertEqual((out / 'report.md').read_text(), '## Review\nNothing to fix.')
            self.assertEqual(json.loads((out / 'meta.json').read_text()), {'total_cost_usd': 1.5})
            self.assertEqual((out / sarif.name).read_text(), '{"runs": []}')

    def test_clean_case_counts_blocking_findings_as_noise(self):
        case = rev.clean_case(self.repo, 'HEAD~1')
        result = rev.judge(case, [('other.py', 1, 'REQUIRED'), ('other.py', 1, 'ADVISORY')])
        self.assertEqual(result['blocking'], 1)
        self.assertFalse(rev.item(case, result))
        self.assertTrue(rev.item(case, rev.judge(case, [])))

    def test_markdown_fallback(self):
        text = '### BLOCKER\n- [CODE-1] [feed.py:3] (confidence: high) drops the first post\n### ADVISORY\n- [CODE-2] [feed.py:1] name\n'
        self.assertEqual([f[:3] for f in rev.markdown_findings(text)], [('feed.py', 3, 'BLOCKER'), ('feed.py', 1, 'ADVISORY')])


class Produce(unittest.TestCase):
    """produce() with a stub `claude` on PATH: a review that did not finish is
    an error, never an empty finding list that scores as a quiet review."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = base / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        (self.repo / 'feed.py').write_text('x = 1\n')
        git(self.repo, 'add', '-A'); git(self.repo, 'commit', '-qm', 'A')
        (self.repo / 'feed.py').write_text('x = 2\n')
        git(self.repo, 'commit', '-qam', 'B')
        self.case = rev.clean_case(self.repo, 'HEAD')
        self.bin = base / 'bin'
        self.bin.mkdir()
        self.path = os.environ['PATH']
        os.environ['PATH'] = f'{self.bin}:{self.path}'

    def tearDown(self):
        os.environ['PATH'] = self.path
        self.tmp.cleanup()

    def stub(self, **meta):
        """A `claude` that records its arguments and prints a stream-json result event."""
        out = self.bin / 'claude'
        event = json.dumps({'type': 'result', **meta})
        out.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {self.bin}/args\ncat <<'EOF'\n{event}\nEOF\n")
        out.chmod(out.stat().st_mode | stat.S_IEXEC)

    def test_session_is_stream_json_verbose_with_no_add_dir(self):
        self.stub(is_error=False, result='**Findings: 0 BLOCKER · 0 REQUIRED · 0 ADVISORY**')
        rev.produce(self.case, self.repo, '1')
        args = (self.bin / 'args').read_text().splitlines()
        self.assertNotIn('--add-dir', args)
        self.assertEqual(args[args.index('--output-format') + 1], 'stream-json')
        self.assertIn('--verbose', args)
        self.assertEqual(args[args.index('--max-budget-usd') + 1], '1')

    def test_review_tools_stay_the_narrow_review_set(self):
        self.stub(is_error=False, result='**Findings: 0 BLOCKER · 0 REQUIRED · 0 ADVISORY**')
        rev.produce(self.case, self.repo, '1')
        args = (self.bin / 'args').read_text().splitlines()
        tools = args[args.index('--allowedTools') + 1:args.index('--max-budget-usd')]
        self.assertEqual(tools, list(rev.REVIEW_TOOLS))
        self.assertNotIn('Edit', tools)

    def test_the_trace_is_kept_beside_the_report_for_the_audit(self):
        self.stub(is_error=False, result='**Findings: 0 BLOCKER · 0 REQUIRED · 0 ADVISORY**')
        out = Path(self.tmp.name) / 'out'
        rev.produce(self.case, self.repo, '1', out=out)
        trace = out / 'trace.jsonl'
        self.assertEqual(json.loads(trace.read_text().splitlines()[-1])['type'], 'result')
        self.assertEqual(rev.sandbox.audit(trace), (False, []))

    def test_the_review_project_holds_a_copy_of_the_harness_not_links(self):
        self.stub(is_error=False, result='**Findings: 0 BLOCKER · 0 REQUIRED · 0 ADVISORY**')
        self.bin.joinpath('claude').write_text(
            "#!/bin/sh\nfind .claude -type l | wc -l > " + f"{self.bin}/links\n"
            "test -f .claude/commands/review.md && echo yes > " + f"{self.bin}/review\n"
            "echo '{\"type\":\"result\",\"is_error\":false,\"result\":\"**Findings: 0 BLOCKER · 0 REQUIRED · 0 ADVISORY**\"}'\n")
        rev.produce(self.case, self.repo, '1')
        self.assertEqual((self.bin / 'links').read_text().strip(), '0')
        self.assertEqual((self.bin / 'review').read_text().strip(), 'yes')

    def test_error_result_is_not_a_quiet_review(self):
        self.stub(is_error=True, result='REVIEW BLOCKED: verification missing')
        with self.assertRaises(RuntimeError):
            rev.produce(self.case, self.repo, '1')

    def test_review_blocked_text_is_not_a_quiet_review(self):
        self.stub(is_error=False, result='**REVIEW BLOCKED** - run /test first')
        with self.assertRaises(RuntimeError):
            rev.produce(self.case, self.repo, '1')

    def test_empty_output_is_not_a_quiet_review(self):
        self.stub(is_error=False, result='')
        with self.assertRaises(RuntimeError):
            rev.produce(self.case, self.repo, '1')

    def test_budget_stop_is_not_a_quiet_review(self):
        self.stub(is_error=False, subtype='error_max_budget_usd', result='**Nothing to fix.**')
        with self.assertRaises(RuntimeError):
            rev.produce(self.case, self.repo, '1')

    def test_count_line_without_parsable_findings_is_not_a_quiet_review(self):
        self.stub(is_error=False, result='**Findings: 1 BLOCKER · 0 REQUIRED · 0 ADVISORY**\n- CODE-1 something odd')
        with self.assertRaises(RuntimeError):
            rev.produce(self.case, self.repo, '1')

    def test_stated_zero_findings_is_a_valid_quiet_review(self):
        self.stub(is_error=False, result='**Findings: 0 BLOCKER · 0 REQUIRED · 0 ADVISORY**\n**Nothing to fix.**')
        findings, _, source = rev.produce(self.case, self.repo, '1')
        self.assertEqual((findings, source), ([], 'markdown'))

    def test_parsed_markdown_findings_are_a_valid_review(self):
        self.stub(is_error=False, result='### REQUIRED\n- [CODE-1] [feed.py:1] wrong\n')
        findings, _, _ = rev.produce(self.case, self.repo, '1')
        self.assertEqual([f[:3] for f in findings], [('feed.py', 1, 'REQUIRED')])

    def test_errored_case_is_reported_and_not_scored(self):
        fixtures = Path(self.tmp.name) / 'fixtures'
        (fixtures / 'quiet').mkdir(parents=True)
        (fixtures / 'quiet' / 'case.json').write_text(json.dumps({'name': 'quiet', **self.case}))
        saved_fixtures, rev.FIXTURES = rev.FIXTURES, fixtures
        self.addCleanup(setattr, rev, 'FIXTURES', saved_fixtures)
        out = Path(self.tmp.name) / 'out'
        self.stub(is_error=True, result='REVIEW BLOCKED')
        rc = rev.main(['--fixture', 'quiet', '--repo', str(self.repo), '--output', str(out)])
        saved = json.loads((out / 'results.json').read_text())
        self.assertEqual(saved['results'], {})
        self.assertIn('error', saved['detail']['quiet'])
        self.assertEqual(rc, 1)


class TagsAndSplit(unittest.TestCase):
    """A case carries behavior tags and a split; a holdout case the baseline passed and a change
    loses makes the change WORSE, whatever the optimization cases gained (ADR 0117)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = base / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        (self.repo / 'feed.py').write_text('x = 1\n')
        git(self.repo, 'add', '-A'); git(self.repo, 'commit', '-qm', 'A')
        self.fixtures = base / 'fixtures'
        self.fixtures.mkdir()
        self.saved, rev.FIXTURES = rev.FIXTURES, self.fixtures
        self.out = base / 'out'

    def tearDown(self):
        rev.FIXTURES = self.saved
        self.tmp.cleanup()

    def new(self, name, *extra):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(rev.main(['--new', name, '--repo', str(self.repo), '--clean', 'HEAD', *extra]), 0)
        return json.loads((self.fixtures / name / 'case.json').read_text())

    def test_new_case_records_tags_and_split(self):
        case = self.new('q1', '--tag', 'tenant', '--tag', 'auth', '--holdout')
        self.assertEqual((case['tags'], case['split']), (['auth', 'tenant'], 'holdout'))
        case = self.new('q2')
        self.assertEqual((case['tags'], case['split']), ([], 'optimization'))

    def test_selection_by_all_tag_and_split(self):
        self.new('q1', '--tag', 'tenant', '--holdout')
        self.new('q2', '--tag', 'auth')
        self.assertEqual(rev.selected([], every=True), ['q1', 'q2'])
        self.assertEqual(rev.selected([], every=True, tags=['tenant']), ['q1'])
        self.assertEqual(rev.selected([], every=True, split='optimization'), ['q2'])
        self.assertEqual(rev.selected(['q2'], tags=['tenant']), [])
        self.assertEqual(rev.selected(['q2', 'q1'], tags=['tenant', 'auth']), ['q2', 'q1'])

    def test_a_lost_holdout_case_is_worse_whatever_else_gained(self):
        base = {'a': True, 'b': False, 'c': False, 'h': True}
        now = {'a': True, 'b': True, 'c': True, 'h': False}
        pair, word, why, lost = rev.compare(base, now, {'h': 'holdout'})
        self.assertEqual((word, lost, pair['wins']), ('WORSE', ['h'], ['b', 'c']))
        self.assertEqual(rev.compare(base, now, {})[1], 'BETTER')           # the same loss, not a holdout case

    def test_tally(self):
        self.assertEqual(rev.tally(['a', 'b', 'c'], {'a': True, 'b': False, 'c': True},
                                   {'a': 'bug', 'b': 'bug', 'c': 'clean'}), 'bugs 1/2, clean 1/1')

    def test_results_carry_split_and_tags_and_the_holdout_line(self):
        self.new('q1', '--tag', 'tenant', '--holdout')
        quiet = Path(self.tmp.name) / 'quiet.sarif'
        quiet.write_text(json.dumps({'runs': []}))
        noisy = Path(self.tmp.name) / 'noisy.sarif'
        noisy.write_text(json.dumps({'runs': [{'results': [{'ruleId': 'CODE-1', 'properties': {'disposition': 'REQUIRED'},
            'locations': [{'physicalLocation': {'artifactLocation': {'uri': 'feed.py'}, 'region': {'startLine': 1}}}]}]}]}))
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rev.main(['--fixture', 'q1', '--findings', str(quiet), '--output', str(self.out)]), 0)
        self.assertIn('Holdout: clean 1/1', out.getvalue())
        self.assertIn('By tag: tenant clean 1/1', out.getvalue())
        saved = json.loads((self.out / 'results.json').read_text())
        self.assertEqual((saved['splits'], saved['tags'], saved['results']), ({'q1': 'holdout'}, {'q1': ['tenant']}, {'q1': True}))
        with redirect_stdout(io.StringIO()) as out:
            rc = rev.main(['--fixture', 'q1', '--findings', str(noisy), '--baseline', str(self.out / 'results.json')])
        self.assertEqual(rc, 1)
        self.assertIn('lost   q1 (holdout)', out.getvalue())
        self.assertIn('Holdout: 1/1 -> 0/1', out.getvalue())
        self.assertIn('WORSE: a holdout case the baseline passed is now lost', out.getvalue())


BUG = {'kind': 'bug', 'change': 'c1', 'targets': {'feed.py': [3]}, 'defect': ['drops the first'],
       'tags': ['order'], 'split': 'holdout'}
CLEAN = {'kind': 'clean', 'change': 'c2', 'targets': {}, 'tags': [], 'split': 'optimization'}
NEAR = ('feed.py', 3, 'BLOCKER', 'The slice drops the first post.')
NEAR_OTHER = ('feed.py', 3, 'REQUIRED', 'Leading spaces are not trimmed.')
FAR = ('feed.py', 40, 'BLOCKER', 'The slice drops the first post.')
ADVISORY = ('feed.py', 3, 'ADVISORY', 'The slice drops the first post.')


class BugsSuite(unittest.TestCase):
    """The review eval as a suite for the eval core: one `/review` per trial, judged by `judge()`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.fixtures = base / 'fixtures'
        saved, rev.FIXTURES = rev.FIXTURES, self.fixtures
        self.addCleanup(setattr, rev, 'FIXTURES', saved)
        for name, case in (('shipped', BUG), ('quiet', CLEAN)):
            (self.fixtures / name).mkdir(parents=True)
            (self.fixtures / name / 'case.json').write_text(json.dumps({'name': name, **case}))
        self.folder = base / 'run' / 'shipped' / 't1'
        self.folder.mkdir(parents=True)
        self.calls = []
        self.suite = rev.BugsSuite(Path('/repo'), 10)

    def play(self, *outcomes, cost=1.25, calls=()):
        """Make `produce()` return, or raise, each outcome in turn: a findings list, or an exception.
        With `calls`, each review leaves a trace of those tool calls, `(tool, input)`, beside its report."""
        plan = list(outcomes)

        def produce(case, repo, budget, out):
            self.calls.append((case['change'], repo, budget, out))
            if calls:
                (out / 'trace.jsonl').write_text('\n'.join(json.dumps(
                    {'type': 'assistant', 'message': {'content': [
                        {'type': 'tool_use', 'id': f'toolu_{n}', 'name': tool, 'input': tool_input}]}})
                    for n, (tool, tool_input) in enumerate(calls)) + '\n')
            outcome = plan.pop(0)
            if isinstance(outcome, Exception):
                (out / 'meta.json').write_text(json.dumps({'total_cost_usd': cost}))
                raise outcome
            return outcome, {'total_cost_usd': cost, 'duration_ms': 4200}, 'sarif'

        patch = mock.patch.object(rev, 'produce', produce)
        patch.start()
        self.addCleanup(patch.stop)

    def trial(self, name='shipped'):
        return self.suite.run_trial({'id': name}, self.folder)

    def test_every_fixture_is_a_case_with_its_split_and_tags(self):
        cases = {c['id']: c for c in self.suite.all_cases()}
        self.assertEqual(sorted(cases), ['quiet', 'shipped'])
        self.assertEqual((cases['shipped']['split'], cases['shipped']['tags']), ('holdout', ['order']))
        self.assertEqual((cases['quiet']['split'], cases['quiet']['tags']), ('optimization', []))

    def test_a_finding_at_the_lines_that_names_the_defect_is_a_caught_trial_that_passes(self):
        self.play([NEAR])
        trial = self.trial()
        self.assertEqual((trial['verdict'], trial['kind'], trial['caught']), ('CAUGHT', 'bug', True))
        self.assertEqual(self.suite.state(trial), 'pass')
        self.assertEqual((trial['cost_usd'], trial['duration_ms'], trial['source']), (1.25, 4200, 'sarif'))

    def test_a_finding_at_the_lines_about_something_else_is_located_and_fails(self):
        self.play([NEAR_OTHER])
        trial = self.trial()
        self.assertEqual((trial['verdict'], self.suite.state(trial)), ('LOCATED', 'fail'))

    def test_a_review_with_no_finding_at_the_lines_is_missed_and_fails(self):
        self.play([FAR, ADVISORY])
        trial = self.trial()
        self.assertEqual((trial['verdict'], self.suite.state(trial)), ('MISSED', 'fail'))

    def test_a_clean_case_passes_without_a_blocking_finding_and_fails_with_one(self):
        self.play([ADVISORY], [FAR])
        quiet, noisy = self.trial('quiet'), self.trial('quiet')
        self.assertEqual((quiet['verdict'], quiet['kind'], self.suite.state(quiet)), ('QUIET', 'clean', 'pass'))
        self.assertEqual((noisy['verdict'], noisy['blocking'], self.suite.state(noisy)), ('NOISY', 1, 'fail'))

    def test_the_trial_folder_and_the_budget_go_to_produce(self):
        self.play([NEAR])
        self.trial()
        self.assertEqual(self.calls, [('c1', Path('/repo'), 10, self.folder)])

    def test_a_trial_with_no_judgement_is_errored(self):
        self.assertEqual(self.suite.state({}), 'errored')

    def test_a_review_that_did_not_finish_raises_so_the_core_records_errored(self):
        self.play(RuntimeError('review did not finish'))
        with self.assertRaises(RuntimeError):
            self.trial()

    def test_the_retry_gets_only_what_the_first_attempt_left_of_the_budget(self):
        self.play(RuntimeError('review did not finish'), [NEAR], cost=7)
        with self.assertRaises(RuntimeError):
            self.trial()
        self.assertEqual(self.trial()['verdict'], 'CAUGHT')
        self.assertEqual([c[2] for c in self.calls], [10, 3])

    def test_a_review_that_died_before_it_saved_its_result_is_costed_from_its_trace(self):
        # run_session() raises on a non-zero exit after it has written the trace and before keep() runs.
        def dies(case, repo, budget, out):
            (out / 'trace.jsonl').write_text('{"type": "assistant"}\n'
                                             '{"type": "result", "subtype": "error_max_turns", "total_cost_usd": 4}\n')
            raise RuntimeError('claude exited 1')

        with mock.patch.object(rev, 'produce', dies), self.assertRaises(RuntimeError):
            self.trial()
        self.play([NEAR])
        self.assertEqual(self.trial()['verdict'], 'CAUGHT')
        self.assertEqual(self.calls[-1][2], 6)

    def test_a_review_that_left_no_cost_anywhere_counts_as_having_spent_the_budget(self):
        def dies(case, repo, budget, out):
            raise subprocess.TimeoutExpired('claude', 1800)

        with mock.patch.object(rev, 'produce', dies), self.assertRaises(subprocess.TimeoutExpired):
            self.trial()
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            self.trial()

    def test_a_bug_case_without_defect_terms_says_it_can_reach_located_at_best(self):
        (self.fixtures / 'bare').mkdir()
        (self.fixtures / 'bare' / 'case.json').write_text(json.dumps({'name': 'bare', **{**BUG, 'defect': []}}))
        self.play([NEAR], [NEAR])
        with redirect_stderr(io.StringIO()) as err:
            trial = self.trial('bare')
            self.trial()
        self.assertEqual((trial['verdict'], err.getvalue().count('bare')), ('LOCATED', 1))
        self.assertIn('no "defect" terms', err.getvalue())

    def test_a_retry_with_nothing_left_is_not_started(self):
        self.play(RuntimeError('review did not finish'), cost=10)
        with self.assertRaises(RuntimeError):
            self.trial()
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            self.trial()
        self.assertEqual(len(self.calls), 1)

    def test_a_review_that_read_the_hidden_checks_is_leaked_and_fails_even_when_it_caught_the_bug(self):
        hidden = '/var/www/html/personal/harness/claude/evals/add-business/hidden/checks.json'
        self.play([NEAR], calls=[('Read', {'file_path': hidden})])
        trial = self.trial()
        self.assertEqual((trial['verdict'], trial['caught']), ('CAUGHT', True))
        self.assertEqual((trial['leaked'], [c['tool'] for c in trial['leaks']]), (True, ['Read']))
        self.assertEqual(self.suite.state(trial), 'fail')

    def test_a_leaked_clean_trial_fails_though_it_is_quiet(self):
        self.play([ADVISORY], calls=[('Bash', {'command': 'cat claude/evals/add-business/reference/x.php'})])
        trial = self.trial('quiet')
        self.assertEqual((trial['verdict'], trial['leaked'], self.suite.state(trial)), ('QUIET', True, 'fail'))

    def test_a_review_that_read_only_project_files_is_not_leaked(self):
        self.play([NEAR], calls=[('Read', {'file_path': 'feed.py'})])
        trial = self.trial()
        self.assertEqual((trial['leaked'], trial['leaks'], self.suite.state(trial)), (False, [], 'pass'))

    def test_a_review_with_no_trace_is_not_leaked(self):
        self.play([NEAR])
        self.assertEqual(self.trial()['leaked'], False)


LOG = """# Observation log

## Shipped bugs

Intro text with `leadbuster deadbee0` in prose, outside the table.

| Found | Ticket that shipped it | Bug | Fix commit | Should have caught it | Why it missed | Eval case |
|---|---|---|---|---|---|---|
| 2026-11-01 | FIX-9 `{fix}` | An unrelated bug that names the fix only in its ticket column | project `0000000a` | 2 | x | none |
| 2026-11-18 | none | The feed drops the first post, with a `[1:]` slice | project `{short}` | 2 AI review | y | `feed-first` |

## Per ticket

| Shipped | Ticket | Bug | Fix commit |
|---|---|---|---|
| 2026-11-20 | FIX-10 | Not a shipped bug | project `1234abcd` |
"""


class AddCase(unittest.TestCase):
    """`bugs add`: a case from a fix commit, or from the "Shipped bugs" row that names it (REQ-022)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo = base / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        (self.repo / 'feed.py').write_text('def order(posts):\n    posts = list(posts)\n    return sorted(posts)[1:]\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'B')
        self.bug = git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'feed.py').write_text('def order(posts):\n    posts = list(posts)\n    return sorted(posts)\n')
        git(self.repo, 'commit', '-qam', 'F')
        self.fix = git(self.repo, 'rev-parse', 'HEAD')
        self.log = base / 'observation-log.md'
        self.log.write_text(LOG.format(fix=self.fix[:8], short=self.fix[:8]))
        self.fixtures = base / 'fixtures'
        self.fixtures.mkdir()
        saved, rev.FIXTURES = rev.FIXTURES, self.fixtures
        self.addCleanup(setattr, rev, 'FIXTURES', saved)

    def add(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = rev.BugsSuite().add(['--repo', str(self.repo), '--log', str(self.log), *args])
        return code, out.getvalue(), err.getvalue()

    def case(self, name):
        return json.loads((self.fixtures / name / 'case.json').read_text())

    def test_the_row_is_found_by_its_fix_commit_column_only(self):
        row = rev.shipped_bug(self.log.read_text(), self.fix)
        self.assertEqual(row['bug'], 'The feed drops the first post, with a `[1:]` slice')
        self.assertIsNone(rev.shipped_bug(self.log.read_text(), 'deadbee'))   # in prose, not in a row
        self.assertIsNone(rev.shipped_bug(self.log.read_text(), '1234abcd'))  # a row of another table

    def test_a_short_or_full_sha_names_the_same_row(self):
        text = self.log.read_text()
        self.assertEqual(rev.shipped_bug(text, self.fix[:8])['bug'], rev.shipped_bug(text, self.fix)['bug'])
        self.assertIsNone(rev.shipped_bug(text, self.fix[:3]))                # too short to name a commit

    def test_from_log_builds_the_case_from_that_fix_with_the_row_text_as_its_description(self):
        code, out, _ = self.add('--from-log', self.fix, '--defect', 'drops the first')
        case = self.case(f'fix-{self.fix[:8]}')
        self.assertEqual((code, case['kind'], case['change'], case['fix']), (0, 'bug', self.bug, self.fix))
        self.assertEqual(case['targets'], {'feed.py': [3]})
        self.assertEqual((case['defect'], case['description']),
                         (['drops the first'], 'The feed drops the first post, with a `[1:]` slice'))
        self.assertIn(f'fix-{self.fix[:8]}', out)

    def test_from_log_takes_the_case_name_when_one_is_given(self):
        self.add('--from-log', self.fix, '--defect', 'x', '--new', 'feed-first')
        self.assertEqual(self.case('feed-first')['kind'], 'bug')

    def test_no_row_exits_2_says_so_and_writes_no_case(self):
        code, _, err = self.add('--from-log', 'deadbee', '--defect', 'x')
        self.assertEqual(code, 2)
        self.assertIn('no Shipped bugs row names deadbee', err)
        self.assertEqual(list(self.fixtures.iterdir()), [])

    def test_a_fix_without_a_defect_term_is_refused_and_writes_no_case(self):
        for args in (('--from-log', self.fix), ('--new', 'plain', '--fix', self.fix)):
            code, _, err = self.add(*args)
            self.assertEqual(code, 2)
            self.assertIn('--defect', err)
        self.assertEqual(list(self.fixtures.iterdir()), [])

    def test_without_from_log_it_takes_the_arguments_of_run_py_new(self):
        code, _, _ = self.add('--new', 'feed-order', '--fix', self.fix, '--defect', 'sorted', '--tag', 'order', '--holdout')
        case = self.case('feed-order')
        self.assertEqual((code, case['change'], case['defect'], case['tags'], case['split']),
                         (0, self.bug, ['sorted'], ['order'], 'holdout'))
        self.assertNotIn('description', case)

    def test_a_clean_case_needs_no_defect_term(self):
        code, _, _ = self.add('--new', 'quiet', '--clean', self.fix)
        self.assertEqual((code, self.case('quiet')['kind']), (0, 'clean'))

    def test_an_unknown_log_file_exits_2(self):
        self.log.unlink()
        code, _, err = self.add('--from-log', self.fix, '--defect', 'x')
        self.assertEqual(code, 2)
        self.assertIn('observation log', err)


class BugsEndToEnd(unittest.TestCase):
    """`eval.py bugs` through the real core and the real BugsSuite, with a stub `claude` on PATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo = base / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        (self.repo / 'feed.py').write_text('x = 1\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'A')
        (self.repo / 'feed.py').write_text('x = 2\n')
        git(self.repo, 'commit', '-qam', 'B')
        change = git(self.repo, 'rev-parse', 'HEAD')
        fixtures = base / 'fixtures'
        for name, case in (('shipped', {'kind': 'bug', 'change': change, 'targets': {'feed.py': [1]}, 'defect': ['wrong']}),
                           ('quiet', {'kind': 'clean', 'change': change, 'targets': {}})):
            (fixtures / name).mkdir(parents=True)
            (fixtures / name / 'case.json').write_text(json.dumps({'name': name, 'tags': [], 'split': 'optimization', **case}))
        saved, rev.FIXTURES = rev.FIXTURES, fixtures
        self.addCleanup(setattr, rev, 'FIXTURES', saved)
        self.root = base / 'harness'
        self.root.mkdir()
        (self.root / '.gitignore').write_text('tools/evals/results/\n')
        git(self.root, 'init', '-q')
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-qm', 'base')
        self.bin = base / 'bin'
        self.bin.mkdir()
        self.addCleanup(os.environ.__setitem__, 'PATH', os.environ['PATH'])
        os.environ['PATH'] = f'{self.bin}:{os.environ["PATH"]}'
        event = json.dumps({'type': 'result', 'is_error': False, 'total_cost_usd': 0.5, 'duration_ms': 900,
                            'result': '### BLOCKER\n- [CODE-1] [feed.py:1] The value is wrong.\n'})
        claude = self.bin / 'claude'
        claude.write_text(f"#!/bin/sh\ncat <<'EOF'\n{event}\nEOF\n")
        claude.chmod(claude.stat().st_mode | stat.S_IEXEC)

    def test_the_suite_runs_its_cases_with_trials_and_ends_the_report_with_the_review_eval_line(self):
        sys.path.insert(0, str(HERE.parent))
        import eval as eval_cli
        registry = {name: {'question': 'q', 'when': 'w', 'cost': None, 'build': None} for name in ('gates', 'tasks', 'recall')}
        registry['bugs'] = {'question': 'q', 'when': 'w', 'cost': None, 'build': lambda: rev.BugsSuite()}
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            code = eval_cli.main(['bugs', '--repo', str(self.repo), '--trials', '2', '--budget', '3'],
                                 suites=registry, root=self.root)
        run = next((self.root / 'tools/evals/results/bugs').iterdir())
        doc = json.loads((run / 'results.json').read_text())
        states = {c['id']: (c['result']['state'], [t['verdict'] for t in c['trials']]) for c in doc['cases']}
        self.assertEqual(states, {'quiet': ('FAIL', ['NOISY', 'NOISY']), 'shipped': ('PASS', ['CAUGHT', 'CAUGHT'])})
        self.assertEqual((code, doc['trials'], doc['cost_usd'], doc['schema']), (0, 2, 2.0, 1))
        self.assertEqual(doc['instruction_hashes'], rev.sandbox.harness_hashes())
        self.assertTrue((run / 'shipped' / 't1' / 'trace.jsonl').is_file())
        self.assertEqual(out.getvalue().rstrip('\n').splitlines()[-1],
                         f'Review-eval: bugs 1/1, clean 0/1; tools/evals/results/bugs/{run.name}')


if __name__ == '__main__':
    unittest.main(verbosity=1)
