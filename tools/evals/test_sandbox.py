#!/usr/bin/env python3
"""The sandbox: the harness copy, the session arguments and the leak audit.
`claude` is never invoked. Runs in CI."""
import json
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

    def test_project_rules_stay_and_harness_rules_go_beside_them(self):
        (self.project / 'CLAUDE.md').write_text('project rules\n')
        sandbox.install_harness(self.project, harness=self.src)
        self.assertEqual((self.project / 'CLAUDE.md').read_text(), 'project rules\n')
        self.assertFalse((self.project / '.claude/CLAUDE.md').exists())
        self.assertEqual((self.project / '.claude/AGENTS.md').read_text(), 'harness rules\n')

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


class SessionArgs(unittest.TestCase):
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
