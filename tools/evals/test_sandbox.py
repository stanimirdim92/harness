#!/usr/bin/env python3
"""The sandbox: the harness copy, the session arguments and the leak audit.
`claude` is never invoked. Runs in CI."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sandbox

HIDDEN = '/var/www/html/personal/harness/claude/evals/add-business/hidden/checks.json'


def tool_use(name, tool_input, parent=None, tool_id='toolu_1'):
    return {'type': 'assistant', 'parent_tool_use_id': parent,
            'message': {'content': [{'type': 'tool_use', 'id': tool_id, 'name': name, 'input': tool_input}]}}


def write_trace(folder, events):
    path = Path(folder) / 'trace.jsonl'
    path.write_text('\n'.join(json.dumps(event) for event in events) + '\n')
    return path


class InstallHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.src = tmp / 'claude'
        for name in sandbox.HARNESS_DIRS:
            (self.src / name).mkdir(parents=True)
            (self.src / name / 'file.md').write_text(f'{name} file\n')
        # An evals folder at the top and nested inside a copied folder.
        (self.src / 'evals/add-business/hidden').mkdir(parents=True)
        (self.src / 'evals/add-business/hidden/checks.json').write_text('{}')
        (self.src / 'skills/nested/evals').mkdir(parents=True)
        (self.src / 'skills/nested/evals/secret.md').write_text('secret\n')
        (self.src / 'skills/nested/SKILL.md').write_text('skill\n')
        (self.src / 'AGENTS.md').write_text('harness rules\n')
        (self.src / 'settings.json').write_text(json.dumps({
            'model': 'opus', 'effortLevel': 'high', 'worktree': {'symlinkDirectories': ['x']},
            'env': {'CLAUDE_CODE_MAX_SUBAGENT_X': '1', 'CLAUDE_CODE_EXPERIMENTAL_Y': '2', 'SECRET_TOKEN': 'no'}}))
        self.project = tmp / 'project'
        self.project.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_the_six_folders_as_real_files(self):
        sandbox.install_harness(self.project, harness=self.src)
        for name in sandbox.HARNESS_DIRS:
            copied = self.project / '.claude' / name / 'file.md'
            self.assertEqual(copied.read_text(), f'{name} file\n')
        self.assertFalse(any(p.is_symlink() for p in (self.project / '.claude').rglob('*')))

    def test_copy_holds_no_evals_folder(self):
        sandbox.install_harness(self.project, harness=self.src)
        found = [p for p in self.project.rglob('*') if p.name == 'evals']
        self.assertEqual(found, [])
        self.assertTrue((self.project / '.claude/skills/nested/SKILL.md').is_file())

    def test_rules_become_claude_md_when_project_has_none(self):
        sandbox.install_harness(self.project, harness=self.src)
        self.assertEqual((self.project / '.claude/CLAUDE.md').read_text(), 'harness rules\n')

    def test_project_rules_stay_and_harness_rules_go_to_dot_claude_claude_md(self):
        (self.project / 'CLAUDE.md').write_text('project rules\n')
        (self.project / 'AGENTS.md').write_text('project agents rules\n')
        sandbox.install_harness(self.project, harness=self.src)
        self.assertEqual((self.project / 'CLAUDE.md').read_text(), 'project rules\n')
        self.assertEqual((self.project / 'AGENTS.md').read_text(), 'project agents rules\n')
        self.assertEqual((self.project / '.claude/CLAUDE.md').read_text(), 'harness rules\n')
        self.assertFalse((self.project / '.claude/AGENTS.md').exists())

    def test_a_project_dot_claude_claude_md_keeps_its_text_and_the_harness_rules_follow(self):
        (self.project / '.claude').mkdir()
        (self.project / '.claude/CLAUDE.md').write_text('own text\n')
        sandbox.install_harness(self.project, harness=self.src)
        self.assertEqual((self.project / '.claude/CLAUDE.md').read_text(),
                         'own text\n\n<!-- harness rules, copied by install_harness() -->\nharness rules\n')

    def test_a_project_dot_claude_claude_md_without_a_final_newline_still_gets_a_blank_line(self):
        (self.project / '.claude').mkdir()
        (self.project / '.claude/CLAUDE.md').write_text('own text')
        sandbox.install_harness(self.project, harness=self.src)
        self.assertTrue((self.project / '.claude/CLAUDE.md').read_text().startswith('own text\n\n<!--'))

    def test_project_agents_survive_and_harness_agents_join_them(self):
        (self.project / '.claude/agents').mkdir(parents=True)
        (self.project / '.claude/agents/file.md').write_text('project agent\n')
        (self.project / '.claude/agents/local.md').write_text('local\n')
        sandbox.install_harness(self.project, harness=self.src)
        self.assertEqual((self.project / '.claude/agents/file.md').read_text(), 'project agent\n')
        self.assertEqual((self.project / '.claude/agents/local.md').read_text(), 'local\n')

    def test_settings_local_carries_model_and_allowed_env_only(self):
        sandbox.install_harness(self.project, harness=self.src)
        settings = json.loads((self.project / '.claude/settings.local.json').read_text())
        self.assertEqual(settings['model'], 'opus')
        self.assertEqual(settings['env'], {'CLAUDE_CODE_MAX_SUBAGENT_X': '1', 'CLAUDE_CODE_EXPERIMENTAL_Y': '2'})
        self.assertEqual(settings['worktree'], {'symlinkDirectories': ['x']})
        self.assertEqual(settings['permissions'], {'defaultMode': 'acceptEdits'})

    def test_a_missing_harness_folder_is_skipped(self):
        (self.src / 'docs/file.md').unlink()
        (self.src / 'docs').rmdir()
        sandbox.install_harness(self.project, harness=self.src)
        self.assertFalse((self.project / '.claude/docs').exists())
        self.assertTrue((self.project / '.claude/commands/file.md').is_file())


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), '-c', 'user.email=t@t', '-c', 'user.name=t', *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class HarnessHashes(unittest.TestCase):
    """The hashes name the files `install_harness()` copies, for `instruction_hashes` (REQ-002)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # A parent named evals is not an evals folder of the harness.
        self.harness = Path(self.tmp.name) / 'evals' / 'claude'
        for rel in ('AGENTS.md', 'settings.json', 'commands/review.md', 'skills/a/SKILL.md',
                    'commands/evals/hidden.md', 'other/x.md'):
            (self.harness / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.harness / rel).write_text(rel)

    def test_each_installed_file_is_hashed_and_no_evals_or_other_file_is(self):
        self.assertEqual(sorted(sandbox.harness_hashes(self.harness)),
                         ['AGENTS.md', 'commands/review.md', 'settings.json', 'skills/a/SKILL.md'])

    def test_a_changed_file_changes_only_its_own_hash(self):
        before = sandbox.harness_hashes(self.harness)
        (self.harness / 'commands/review.md').write_text('changed')
        after = sandbox.harness_hashes(self.harness)
        self.assertEqual([k for k in before if before[k] != after[k]], ['commands/review.md'])

    def test_the_hashes_name_what_the_install_copies(self):
        project = Path(self.tmp.name) / 'project'
        project.mkdir()
        (self.harness / 'settings.json').write_text(json.dumps({'model': 'opus', 'env': {}}))
        sandbox.install_harness(project, harness=self.harness)
        copied = {str(p.relative_to(project / '.claude')) for p in (project / '.claude').rglob('*')
                  if p.is_file() and p.name in ('review.md', 'SKILL.md')}
        self.assertEqual(copied, {'commands/review.md', 'skills/a/SKILL.md'})
        self.assertTrue(copied <= set(sandbox.harness_hashes(self.harness)))


class RepoProject(unittest.TestCase):
    """The project a run of a repo-backed fixture gets: the repository's files at a
    commit, the harness beside the project's own `.claude`, and a one-commit history."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.repo = tmp / 'app'
        (self.repo / 'docs/specs').mkdir(parents=True)
        (self.repo / '.claude/agents').mkdir(parents=True)
        (self.repo / 'docs/specs/LD-1-SPEC.md').write_text('old spec\n')
        (self.repo / '.claude/agents/local-helper.md').write_text('project agent\n')
        (self.repo / 'CLAUDE.md').write_text('project rules\n')
        (self.repo / 'Ticker.php').write_text('<?php // before\n')
        git(self.repo, 'init', '-q')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'base')
        self.base = git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'Shipped.php').write_text('<?php // the implementation\n')
        (self.repo / 'docs/specs/LD-2-SPEC.md').write_text('the final spec\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'LD-2: shipped')
        self.harness = tmp / 'claude'
        (self.harness / 'agents').mkdir(parents=True)
        (self.harness / 'agents/executor.md').write_text('harness agent\n')
        (self.harness / 'AGENTS.md').write_text('harness rules\n')
        (self.harness / 'settings.json').write_text(json.dumps({'model': 'opus', 'env': {}}))
        self.project = tmp / 'project'
        sandbox.export_repo(self.project, self.repo, self.base)
        sandbox.install_harness(self.project, harness=self.harness)
        sandbox.commit_baseline(self.project)

    def tearDown(self):
        self.tmp.cleanup()

    def test_files_at_the_commit_without_the_future(self):
        self.assertTrue((self.project / 'Ticker.php').is_file())
        self.assertFalse((self.project / 'Shipped.php').exists())
        self.assertFalse((self.project / 'docs/specs/LD-2-SPEC.md').exists())

    def test_export_ignore_paths_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'app'
            (repo / 'tests').mkdir(parents=True)
            (repo / 'tests/Pest.php').write_text('<?php\n')
            (repo / '.gitattributes').write_text('/tests export-ignore\n')
            git(repo, 'init', '-q')
            git(repo, 'add', '-A')
            git(repo, 'commit', '-qm', 'base')
            sandbox.export_repo(Path(tmp) / 'project', repo, 'HEAD')
            self.assertTrue((Path(tmp) / 'project/tests/Pest.php').is_file())

    def test_no_history_reaches_the_run(self):
        self.assertEqual(git(self.project, 'rev-list', '--count', 'HEAD'), '1')
        self.assertNotIn('shipped', git(self.project, 'log', '--all', '--format=%s'))

    def test_the_throwaway_index_is_gone(self):
        self.assertFalse((self.project.parent / 'export.index').exists())

    def test_project_config_kept_and_harness_merged_beside_it(self):
        agents = self.project / '.claude/agents'
        self.assertEqual((agents / 'local-helper.md').read_text(), 'project agent\n')
        self.assertEqual((agents / 'executor.md').read_text(), 'harness agent\n')
        self.assertEqual((self.project / 'CLAUDE.md').read_text(), 'project rules\n')
        self.assertEqual((self.project / '.claude/CLAUDE.md').read_text(), 'harness rules\n')
        self.assertTrue((self.project / '.claude/settings.local.json').is_file())

    def test_the_baseline_commit_holds_the_installed_harness(self):
        tracked = git(self.project, 'ls-files').splitlines()
        self.assertIn('.claude/agents/executor.md', tracked)
        self.assertIn('Ticker.php', tracked)

    def test_a_commit_that_does_not_exist_stops_the_export(self):
        with self.assertRaises(subprocess.CalledProcessError):
            sandbox.export_repo(Path(self.tmp.name) / 'other', self.repo, 'nosuchcommit')


class RunSession(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, *events, code=0, trace=None):
        lines = ''.join(json.dumps(e) + '\n' for e in events)
        script = f"import sys; sys.stdout.write({lines!r}); sys.exit({code})"
        return sandbox.run_session([sys.executable, '-c', script], self.dir, trace=trace)

    def test_returns_the_result_event(self):
        result = self.session({'type': 'system'}, {'type': 'result', 'result': 'done', 'total_cost_usd': 0.5})
        self.assertEqual((result['result'], result['total_cost_usd']), ('done', 0.5))

    def test_keeps_the_whole_stream_as_the_trace_for_audit(self):
        trace = self.dir / 'out' / 'trace.jsonl'
        self.session(tool_use('Read', {'file_path': HIDDEN}), {'type': 'result', 'result': 'x'}, trace=trace)
        self.assertEqual(len(trace.read_text().splitlines()), 2)
        self.assertTrue(sandbox.audit(trace)[0])

    def test_a_failing_session_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, 'exited 3'):
            self.session({'type': 'result', 'result': 'x'}, code=3)

    def test_a_stream_without_a_result_event_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, 'no result'):
            self.session({'type': 'system'})

    def test_the_trace_is_kept_even_when_the_session_fails(self):
        trace = self.dir / 'trace.jsonl'
        with self.assertRaises(RuntimeError):
            self.session({'type': 'system'}, code=1, trace=trace)
        self.assertTrue(trace.is_file())


class SessionArgs(unittest.TestCase):
    def test_a_caller_can_narrow_the_allowed_tools(self):
        args = sandbox.session_args('p', 1, allowed_tools=('Read', 'Bash(git *)'))
        start = args.index('--allowedTools')
        self.assertEqual(args[start + 1:start + 3], ['Read', 'Bash(git *)'])
        self.assertEqual(args[start + 3], '--max-budget-usd')

    def test_no_add_dir_at_all(self):
        args = sandbox.session_args('/spec X-1', 3)
        self.assertNotIn('--add-dir', args)

    def test_no_value_names_the_harness_or_its_evals(self):
        args = sandbox.session_args('/spec X-1', 3, resume='abc')
        harness = str(sandbox.HARNESS)
        for value in args[2:]:
            self.assertNotIn('claude/evals', value)
            self.assertNotIn(harness, value)

    def test_stream_json_with_verbose_and_the_budget(self):
        args = sandbox.session_args('/spec X-1', 3)
        self.assertEqual(args[:3], ['claude', '-p', '/spec X-1'])
        self.assertEqual(args[args.index('--output-format') + 1], 'stream-json')
        self.assertIn('--verbose', args)
        self.assertEqual(args[args.index('--max-budget-usd') + 1], '3')
        self.assertEqual(args[args.index('--setting-sources') + 1], 'project,local')

    def test_resume_is_passed_only_when_given(self):
        self.assertNotIn('--resume', sandbox.session_args('p', 1))
        args = sandbox.session_args('p', 1, resume='abc')
        self.assertEqual(args[args.index('--resume') + 1], 'abc')


class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def audit(self, events):
        return sandbox.audit(write_trace(self.tmp.name, events))

    def test_read_of_a_hidden_file_is_leaked(self):
        leaked, calls = self.audit([tool_use('Read', {'file_path': HIDDEN})])
        self.assertTrue(leaked)
        self.assertEqual([(c['tool'], c['subagent']) for c in calls], [('Read', False)])
        self.assertIn('hidden/checks.json', calls[0]['text'])

    def test_an_event_whose_message_is_a_string_is_skipped_not_a_crash(self):
        # A real trace holds `system` events such as a permission decision whose `message` is text.
        note = {'type': 'system', 'subtype': 'permission', 'message': 'Tilde in assignment value'}
        leaked, calls = self.audit([note, tool_use('Read', {'file_path': HIDDEN}), 'a bare string', ['a', 'list']])
        self.assertEqual((leaked, len(calls)), (True, 1))
        self.assertEqual(self.audit([note]), (False, []))

    def test_bash_naming_the_hidden_folder_is_leaked(self):
        leaked, calls = self.audit([tool_use('Bash', {'command': 'cat evals/add-business/hidden/api/dup.test.php'})])
        self.assertTrue(leaked)
        self.assertEqual(calls[0]['tool'], 'Bash')

    def test_bash_inside_a_subagent_is_leaked_and_marked(self):
        command = 'cat /var/www/html/personal/harness/claude/evals/add-business/hidden/api/dup.test.php'
        leaked, calls = self.audit([tool_use('Bash', {'command': command}, parent='toolu_parent')])
        self.assertTrue(leaked)
        self.assertEqual(calls[0]['subagent'], True)

    def test_reference_folder_is_leaked(self):
        leaked, _ = self.audit([tool_use('Grep', {'pattern': 'x', 'path': 'evals/add-business/reference'})])
        self.assertTrue(leaked)

    def test_any_path_under_claude_evals_is_leaked(self):
        leaked, _ = self.audit([tool_use('Glob', {'pattern': '/h/claude/evals/**/*.md'})])
        self.assertTrue(leaked)

    def test_sandbox_and_claude_files_are_clean(self):
        events = [
            tool_use('Read', {'file_path': '/tmp/p/.claude/commands/spec.md'}, tool_id='a'),
            tool_use('Read', {'file_path': '/tmp/p/.claude/skills/spec-driven-development/SKILL.md'}, parent='x', tool_id='b'),
            tool_use('Bash', {'command': 'python3 .claude/skills/y/check-spec.py docs/specs/X-SPEC.md'}, tool_id='c'),
            tool_use('Grep', {'pattern': 'evals', 'path': '/tmp/p/app'}, tool_id='d'),
        ]
        leaked, calls = self.audit(events)
        self.assertFalse(leaked)
        self.assertEqual(calls, [])

    def test_text_that_only_mentions_a_path_is_not_a_call(self):
        event = {'type': 'assistant', 'parent_tool_use_id': None,
                 'message': {'content': [{'type': 'text', 'text': 'I will not read claude/evals/add-business/hidden'}]}}
        self.assertFalse(self.audit([event])[0])

    def test_lines_that_are_not_json_events_are_skipped(self):
        path = Path(self.tmp.name) / 'trace.jsonl'
        path.write_text('not json\n' + json.dumps(tool_use('Read', {'file_path': HIDDEN})) + '\n')
        self.assertTrue(sandbox.audit(path)[0])


if __name__ == '__main__':
    unittest.main()
