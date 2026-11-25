#!/usr/bin/env python3
"""Fixture tests for tools/checks/check-eval-trailer.py (REQ-017)."""
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'checks' / 'check-eval-trailer.py'
spec = importlib.util.spec_from_file_location('cet', SCRIPT)
cet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cet)

WATCHED = ['claude/commands/build.md', 'claude/agents/*.md']
ZERO = '0' * 40


class EvalTrailer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.commit('base', 'README.md')
        self.base = self.git('rev-parse', 'HEAD')

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, message, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a') as fh:
            fh.write(message + '\n')
        self.git('add', path)
        self.git('commit', '-q', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def bad(self, start=None):
        return [b[1] for b in cet.missing(f'{self.base}..HEAD', WATCHED, start or self.base)]

    def test_watched_commit_without_a_trailer_fails(self):
        self.commit('missing', 'claude/commands/build.md')
        self.assertEqual(self.bad(), ['missing'])

    def test_bare_not_run_fails(self):
        self.commit('lazy\n\nEval: not run', 'claude/commands/build.md')
        self.commit('colon only\n\nEval: not run:', 'claude/commands/build.md')
        self.assertEqual(self.bad(), ['colon only', 'lazy'])

    def test_not_run_with_a_reason_passes(self):
        self.commit('dash\n\nEval: not run - wording only', 'claude/commands/build.md')
        self.commit('colon\n\nEval: Not run: typo', 'claude/agents/executor.md')
        self.assertEqual(self.bad(), [])

    def test_a_result_line_passes(self):
        self.commit('result\n\nEval: gates 51/60 PASS -> 55/60 PASS, flaky 6 -> 2 (BETTER); run', 'claude/commands/build.md')
        self.assertEqual(self.bad(), [])

    def test_unwatched_commit_needs_no_trailer(self):
        self.commit('docs only', 'docs/x.md')
        self.commit('other command', 'claude/commands/other.md')
        self.assertEqual(self.bad(), [])

    def test_glob_in_the_watched_list_matches(self):
        self.commit('glob', 'claude/agents/executor.md')
        self.assertEqual(self.bad(), ['glob'])

    def test_review_eval_alone_does_not_count(self):
        self.commit('only review\n\nReview-eval: bugs 5/8 -> 6/8 (BETTER)', 'claude/commands/build.md')
        self.assertEqual(self.bad(), ['only review'])

    def test_both_trailers_pass(self):
        self.commit('both\n\nEval: gates 51/60 PASS, flaky 6; run\nReview-eval: not run - wording only',
                    'claude/commands/build.md')
        self.assertEqual(self.bad(), [])

    def test_eval_line_outside_the_last_paragraph_does_not_count(self):
        self.commit('early\n\nEval: gates 51/60 PASS, flaky 6; run\n\nRefs: HR-2', 'claude/commands/build.md')
        self.assertEqual(self.bad(), ['early'])

    def test_merge_commits_are_not_checked(self):
        self.git('checkout', '-q', '-b', 'side')
        self.commit('side\n\nEval: not run - side work', 'claude/commands/build.md')
        self.git('checkout', '-q', 'main')
        self.commit('main work', 'docs/y.md')
        self.git('merge', '--no-ff', '-q', '-m', 'merge side', 'side')
        self.assertEqual(self.bad(), [])

    def test_commits_before_the_rule_are_skipped(self):
        self.commit('old', 'claude/commands/build.md')
        start = self.commit('add the check', 'tools/checks/check-eval-trailer.py')
        self.commit('new', 'claude/commands/build.md')
        self.assertEqual(self.bad(start), ['new'])

    def test_the_commit_that_adds_the_check_is_checked(self):
        self.commit('old', 'claude/commands/build.md')
        Path('claude/commands/build.md').write_text('changed\n')
        Path('tools/checks').mkdir(parents=True)
        Path('tools/checks/check-eval-trailer.py').write_text('x\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'adds the check and edits a watched file')
        start = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.bad(start), ['adds the check and edits a watched file'])

    def test_start_commit_is_the_one_that_added_the_script(self):
        self.assertIsNone(cet.start_commit())
        self.commit('old', 'claude/commands/build.md')
        start = self.commit('add the check', cet.SCRIPT_PATH)
        self.commit('later edit', cet.SCRIPT_PATH)
        self.assertEqual(cet.start_commit(), start)

    def test_no_start_commit_means_nothing_is_checked(self):
        self.commit('old', 'claude/commands/build.md')
        self.assertEqual([b[1] for b in cet.missing(f'{self.base}..HEAD', WATCHED, None)], [])

    def test_main_reports_a_failure_with_exit_1(self):
        self.commit('adds the check\n\nEval: not run - adds the check', cet.SCRIPT_PATH)
        self.commit('missing', 'claude/commands/build.md')
        Path('watched.txt').write_text('# files\n\nclaude/commands/build.md\n')
        with redirect_stdout(io.StringIO()) as out:
            code = cet.main(['--range', f'{self.base}..HEAD', '--watched', 'watched.txt'])
        self.assertEqual(code, 1)
        self.assertIn('missing', out.getvalue())
        self.assertIn('claude/commands/build.md', out.getvalue())

    def test_main_passes_a_clean_range_and_a_new_branch(self):
        self.commit('adds the check\n\nEval: not run - adds the check', cet.SCRIPT_PATH)
        Path('watched.txt').write_text('claude/commands/build.md\n')
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cet.main(['--range', f'{self.base}..HEAD', '--watched', 'watched.txt']), 0)
            self.assertEqual(cet.main(['--range', f'{ZERO}..HEAD', '--watched', 'watched.txt']), 0)
        self.assertIn('new branch', out.getvalue())

    def test_main_exits_2_on_a_git_error(self):
        Path('watched.txt').write_text('claude/commands/build.md\n')
        with redirect_stderr(io.StringIO()) as err:
            code = cet.main(['--range', 'nosuchrev..HEAD', '--watched', 'watched.txt'])
        self.assertEqual(code, 2)
        self.assertIn('cannot read', err.getvalue())

    def test_main_exits_2_when_the_watched_file_is_missing(self):
        with redirect_stderr(io.StringIO()):
            code = cet.main(['--range', f'{self.base}..HEAD', '--watched', 'nowhere.txt'])
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main(verbosity=1)
