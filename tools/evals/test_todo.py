#!/usr/bin/env python3
"""`eval.py todo`: a temp git repository and a sample observation log. No model runs; `claude` is not on PATH."""
import contextlib
import io
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import eval as eval_cli
import todo

HERE = Path(__file__).resolve().parent

LOG = """# Observation log

## Plan recall

| Scored | Ticket | Recall (existing) | Recall (all) | Precision | Changed / excluded | Misses | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-03 | LD-441 | 100% | 88% | 88% | 8 / 3 | none | scored |
| 2026-10-07 | LD-380 (harness-test plan) | 69% | 60% | 60% | 43 / 5 | none | scored |

## Shipped bugs

One row per bug found after merge. Prose may name `deadbee`.

| Found | Ticket that shipped it | Bug | Fix commit | Should have caught it | Why it missed | Eval case |
|---|---|---|---|---|---|---|
| 2026-11-18 | none | search drops short words | leadbuster `a47f7cfd` | 2 AI review | missed | `ld-585` |
| 2026-11-20 | LD-500 | empty case column | leadbuster `b12c34d` | 1 verification | missed | |
| 2026-11-21 | LD-501 | dash case column | leadbuster `c99aa00` | 1 verification | missed | — |

## Per ticket
"""


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), '-c', 'user.email=t@t', '-c', 'user.name=t', *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class TodoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / 'project'
        self.repo.mkdir()
        git(self.repo, 'init', '-q', '-b', 'main')
        self.log = self.tmp / 'observation-log.md'
        self.log.write_text(LOG)

    def plan(self, ticket, status='Approved', todo_file=False):
        tasks = self.repo / 'docs' / 'tasks'
        tasks.mkdir(parents=True, exist_ok=True)
        (tasks / f'{ticket}-plan.md').write_text(f'# Implementation Plan: {ticket}\n\nStatus: {status}\n')
        if todo_file:
            (tasks / f'{ticket}-todo.md').write_text('# todo\n')

    def commit(self, subject):
        (self.repo / 'f.txt').write_text(subject)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', subject)
        return git(self.repo, 'rev-parse', 'HEAD')

    def run_todo(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = todo.main(['--repo', str(self.repo), '--log', str(self.log), *flags])
        return code, out.getvalue(), err.getvalue()

    def test_skipped_recall_is_listed_with_a_ready_command(self):
        self.plan('LD-600', todo_file=True)
        self.commit('Base')
        first = self.commit('Add the ticker (LD-600 T001)')
        self.commit('Sort the ticker (LD-600 T002)')
        code, out, _ = self.run_todo()
        self.assertEqual(code, 0)
        line = next(l for l in out.splitlines() if 'eval.py recall' in l)
        self.assertIn('--ticket LD-600 --subject-only', line)
        self.assertIn(f'--repo {self.repo}', line)
        self.assertIn('--plan docs/tasks/LD-600-plan.md --plan docs/tasks/LD-600-todo.md', line)
        self.assertIn(f'--range {first[:12]}^..main', line)

    def test_the_recall_command_runs_plan_recall_on_the_ticket_commits(self):
        self.plan('LD-600')
        self.commit('Base')
        (self.repo / 'a.py').write_text('x')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'Add a (LD-600 T001)')
        command = shlex.split(todo.collect(self.repo, self.log)['tickets'][0]['command'])
        self.assertEqual(command[:3], ['python3', str(HERE / 'eval.py'), 'recall'])
        done = subprocess.run([sys.executable, *command[1:], '--show-commits'], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('Add a (LD-600 T001)', done.stdout)

    def test_a_ticket_that_starts_at_the_root_commit_gets_a_range_git_accepts(self):
        self.plan('LD-600')
        self.commit('Add it (LD-600 T001)')
        command = shlex.split(todo.collect(self.repo, self.log)['tickets'][0]['command'])
        done = subprocess.run([sys.executable, *command[1:], '--show-commits'], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('Add it (LD-600 T001)', done.stdout)

    def test_ticket_without_a_shipped_commit_is_not_listed(self):
        self.plan('LD-601')
        self.commit('Something else (LD-602 T001)')
        _, out, _ = self.run_todo()
        self.assertNotIn('LD-601', out)

    def test_a_ticket_id_that_is_a_prefix_of_another_is_not_shipped(self):
        self.plan('LD-60')
        self.commit('Add the ticker (LD-600 T001)')
        _, out, _ = self.run_todo()
        self.assertNotIn('LD-60 ', out)
        self.assertNotIn('--ticket LD-60 ', out)

    def test_commit_off_the_default_branch_is_not_shipped(self):
        self.plan('LD-603')
        self.commit('Base')
        git(self.repo, 'checkout', '-q', '-b', 'LD-603')
        self.commit('Add it (LD-603 T001)')
        git(self.repo, 'checkout', '-q', 'main')
        _, out, _ = self.run_todo()
        self.assertNotIn('LD-603', out)

    def test_plan_that_is_not_approved_is_not_listed(self):
        self.plan('LD-604', status='Needs replan')
        self.commit('Add it (LD-604 T001)')
        _, out, _ = self.run_todo()
        self.assertNotIn('LD-604', out)

    def test_ticket_with_a_recall_row_is_not_listed(self):
        self.plan('LD-441')
        self.plan('LD-380')
        self.commit('Add it (LD-441 T001)')
        self.commit('Add it too (LD-380 T001)')
        _, out, _ = self.run_todo()
        self.assertNotIn('LD-441', out)
        self.assertNotIn('LD-380', out)

    def test_bug_rows_without_a_case_are_listed(self):
        _, out, _ = self.run_todo()
        self.assertIn(f'eval.py bugs add --repo {self.repo} --from-log b12c34d --defect <term>', out)
        self.assertIn('--from-log c99aa00 --defect <term>', out)
        self.assertNotIn('a47f7cfd', out)

    def test_no_docs_tasks_lists_the_bug_rows_only(self):
        code, out, _ = self.run_todo()
        self.assertEqual(code, 0)
        self.assertNotIn('eval.py recall', out)
        self.assertIn('b12c34d', out)

    def test_nothing_missing_says_so(self):
        self.log.write_text(LOG.replace('| 2026-11-20 | LD-500 | empty case column | leadbuster `b12c34d` | 1 verification | missed | |',
                                        '| 2026-11-20 | LD-500 | empty case column | leadbuster `b12c34d` | 1 verification | missed | `ld-500` |')
                            .replace('| missed | — |', '| missed | `ld-501` |'))
        self.plan('LD-441')
        self.commit('Add it (LD-441 T001)')
        code, out, _ = self.run_todo()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), 'nothing to catch up')

    def test_count_prints_tickets_then_bugs_only(self):
        self.plan('LD-600')
        self.commit('Add it (LD-600 T001)')
        code, out, _ = self.run_todo('--count')
        self.assertEqual((code, out), (0, '1 2\n'))

    def test_count_is_zero_zero_when_nothing_is_missing(self):
        self.log.write_text(LOG.replace('| |\n', '| `x` |\n').replace('| — |', '| `y` |'))
        code, out, _ = self.run_todo('--count')
        self.assertEqual((code, out), (0, '0 0\n'))

    def test_unreadable_log_exits_zero_and_counts_nothing(self):
        self.plan('LD-600')
        self.commit('Add it (LD-600 T001)')
        self.log.unlink()
        code, out, err = self.run_todo('--count')
        self.assertEqual((code, out), (0, '0 0\n'))
        self.assertIn('observation log', err)

    def test_a_log_without_the_plan_recall_table_lists_no_ticket(self):
        self.plan('LD-600')
        self.commit('Add it (LD-600 T001)')
        self.log.write_text(LOG.replace('## Plan recall', '## Something else'))
        code, out, err = self.run_todo('--count')
        self.assertEqual((code, out), (0, '0 0\n'))
        self.assertIn('Plan recall', err)

    def test_a_log_without_the_shipped_bugs_table_lists_nothing(self):
        self.log.write_text('# Observation log\n\nno tables\n')
        code, out, err = self.run_todo()
        self.assertEqual((code, out), (0, ''))
        self.assertIn('Shipped bugs', err)

    def test_runs_through_eval_py_with_no_claude_on_path(self):
        bin_dir = self.tmp / 'bin'
        bin_dir.mkdir()
        for tool in ('git', 'python3'):
            (bin_dir / tool).symlink_to(shutil.which(tool))
        self.assertIsNone(shutil.which('claude', path=str(bin_dir)))
        self.plan('LD-600')
        self.commit('Add it (LD-600 T001)')
        done = subprocess.run([sys.executable, str(HERE / 'eval.py'), 'todo', '--repo', str(self.repo),
                               '--log', str(self.log)],
                              env={'PATH': str(bin_dir), 'HOME': str(self.tmp)}, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('--ticket LD-600 --subject-only', done.stdout)

    def test_eval_py_routes_todo(self):
        self.plan('LD-600')
        self.commit('Add it (LD-600 T001)')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = eval_cli.main(['todo', '--repo', str(self.repo), '--log', str(self.log), '--count'])
        self.assertEqual((code, out.getvalue()), (0, '1 2\n'))


if __name__ == '__main__':
    unittest.main()
