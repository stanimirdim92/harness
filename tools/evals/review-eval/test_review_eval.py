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
import tempfile
import unittest
from contextlib import redirect_stdout
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

    def play(self, *outcomes, cost=1.25):
        """Make `produce()` return, or raise, each outcome in turn: a findings list, or an exception."""
        plan = list(outcomes)

        def produce(case, repo, budget, out):
            self.calls.append((case['change'], repo, budget, out))
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

    def test_a_retry_with_nothing_left_is_not_started(self):
        self.play(RuntimeError('review did not finish'), cost=10)
        with self.assertRaises(RuntimeError):
            self.trial()
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            self.trial()
        self.assertEqual(len(self.calls), 1)

    def test_each_installed_harness_file_is_hashed_and_the_evals_are_not(self):
        harness = Path(self.tmp.name) / 'claude'
        for rel in ('AGENTS.md', 'settings.json', 'commands/review.md', 'skills/a/SKILL.md', 'evals/hidden/check.sh', 'other/x.md'):
            (harness / rel).parent.mkdir(parents=True, exist_ok=True)
            (harness / rel).write_text(rel)
        before = rev.harness_hashes(harness)
        self.assertEqual(sorted(before), ['AGENTS.md', 'commands/review.md', 'settings.json', 'skills/a/SKILL.md'])
        (harness / 'commands/review.md').write_text('changed')
        after = rev.harness_hashes(harness)
        self.assertEqual([k for k in before if before[k] != after[k]], ['commands/review.md'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
