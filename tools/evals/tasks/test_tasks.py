#!/usr/bin/env python3
"""The Bash-sandbox probe: its written deny paths and its record parser.
`claude` is never invoked. Runs in CI."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import probe_sandbox as probe

HARNESS_ROOT = '/var/www/html/personal/harness/claude'
TICKET = f'{HARNESS_ROOT}/evals/add-business/ticket.md'
MARKER = 'Add a business'
CHECK_SPEC = 'python3 ~/.claude/skills/spec-driven-development/scripts/check-spec.py docs/specs/SAMPLE-SPEC.md'
CHECK_SPEC_OUT = 'check-spec: 0 failure(s), 0 warning(s)'


def call(tool_id, command, parent=None, name='Bash'):
    return {'type': 'assistant', 'parent_tool_use_id': parent,
            'message': {'content': [{'type': 'tool_use', 'id': tool_id, 'name': name, 'input': {'command': command}}]}}


def reply(tool_id, text, is_error=False, parent=None):
    block = {'type': 'tool_result', 'tool_use_id': tool_id, 'content': text}
    if is_error:
        block['is_error'] = True
    return {'type': 'user', 'parent_tool_use_id': parent, 'message': {'content': [block]}}


def trace_file(folder, events):
    path = Path(folder) / 'trace.jsonl'
    path.write_text('\n'.join(json.dumps(event) for event in events) + '\n')
    return path


REFUSED = f'cat: {TICKET}: No such file or directory'


def session_cat(text=REFUSED, is_error=True):
    return [call('s1', f'cat {TICKET}'), reply('s1', text, is_error)]


def subagent_cat(text=REFUSED, is_error=True):
    return [call('a0', 'spawn', name='Agent'),
            call('a1', f'cat {TICKET}', parent='a0'), reply('a1', text, is_error, parent='a0')]


def check_spec_run(text=CHECK_SPEC_OUT, is_error=False):
    return [call('c1', CHECK_SPEC), reply('c1', text, is_error)]


class DenyPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.harness = tmp / 'repo' / 'claude'
        for name in ('evals/add-business', 'skills', 'commands', 'hooks', 'references', 'agents'):
            (self.harness / name).mkdir(parents=True)
        self.home = tmp / 'home' / '.claude'
        self.home.mkdir(parents=True)
        for name in ('skills', 'commands', 'hooks', 'references', 'agents'):
            (self.home / name).symlink_to(self.harness / name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_denies_the_evals_folder_by_its_repository_path(self):
        paths = probe.deny_paths(self.harness, self.home)
        self.assertIn(str((self.harness / 'evals').resolve()), paths)

    def test_denies_nothing_outside_the_evals_folder(self):
        evals = (self.harness / 'evals').resolve()
        for path in probe.deny_paths(self.harness, self.home):
            self.assertTrue(Path(path).resolve() == evals or evals in Path(path).resolve().parents, path)

    def test_the_stage_script_links_are_not_denied(self):
        paths = probe.deny_paths(self.harness, self.home)
        for name in ('skills', 'commands', 'hooks', 'references', 'agents'):
            self.assertNotIn(str(self.home / name), paths)
            self.assertNotIn(str((self.harness / name).resolve()), paths)

    def test_a_home_path_that_resolves_into_evals_is_denied_too(self):
        (self.home / 'evals').symlink_to(self.harness / 'evals')
        paths = probe.deny_paths(self.harness, self.home)
        self.assertIn(str(self.home / 'evals'), paths)
        self.assertIn(str((self.harness / 'evals').resolve()), paths)

    def test_a_home_path_into_a_subfolder_of_evals_is_denied_too(self):
        (self.home / 'ab').symlink_to(self.harness / 'evals/add-business')
        self.assertIn(str(self.home / 'ab'), probe.deny_paths(self.harness, self.home))

    def test_the_whole_repository_is_never_denied(self):
        paths = probe.deny_paths(self.harness, self.home)
        self.assertNotIn(str(self.harness.resolve()), paths)
        self.assertNotIn(str(self.harness.resolve().parent), paths)


class SandboxSetting(unittest.TestCase):
    def test_setting_holds_the_confirmed_keys_and_the_deny_list(self):
        setting = probe.sandbox_setting(['/x/claude/evals'])
        self.assertEqual(setting['sandbox']['enabled'], True)
        self.assertEqual(setting['sandbox']['filesystem'], {'denyRead': ['/x/claude/evals']})

    def test_the_session_cannot_leave_the_sandbox_and_cannot_start_without_it(self):
        sandbox = probe.sandbox_setting(['/x'])['sandbox']
        self.assertIs(sandbox['allowUnsandboxedCommands'], False)
        self.assertIs(sandbox['failIfUnavailable'], True)

    def test_writing_it_keeps_the_rest_of_settings_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / '.claude/settings.local.json'
            local.parent.mkdir()
            local.write_text(json.dumps({'model': 'opus', 'permissions': {'defaultMode': 'acceptEdits'}}))
            probe.write_setting(tmp, ['/x/claude/evals'])
            written = json.loads(local.read_text())
        self.assertEqual(written['model'], 'opus')
        self.assertEqual(written['permissions'], {'defaultMode': 'acceptEdits'})
        self.assertEqual(written['sandbox']['filesystem']['denyRead'], ['/x/claude/evals'])


class RecordParser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, *parts):
        events = [event for part in parts for event in part]
        return probe.parse_record(trace_file(self.tmp.name, events), TICKET, MARKER)

    def test_both_reads_refused_and_check_spec_run_is_pass(self):
        record = self.record(session_cat(), subagent_cat(), check_spec_run())
        self.assertEqual(record['result'], 'pass')
        self.assertEqual((record['session_cat'], record['subagent_cat'], record['check_spec']),
                         ('refused', 'refused', 'ran'))

    def test_check_spec_refused_is_fail(self):
        refused = check_spec_run('python3: can\'t open file: Permission denied', is_error=True)
        record = self.record(session_cat(), subagent_cat(), refused)
        self.assertEqual(record['check_spec'], 'refused')
        self.assertEqual(record['result'], 'fail')

    def test_the_session_cat_that_prints_the_file_is_fail(self):
        record = self.record(session_cat(f'# {MARKER}\nbody', is_error=False), subagent_cat(), check_spec_run())
        self.assertEqual(record['session_cat'], 'read')
        self.assertEqual(record['result'], 'fail')

    def test_the_subagent_cat_that_prints_the_file_is_fail(self):
        record = self.record(session_cat(), subagent_cat(f'# {MARKER}\nbody', is_error=False), check_spec_run())
        self.assertEqual(record['subagent_cat'], 'read')
        self.assertEqual(record['result'], 'fail')

    def test_no_subagent_cat_is_fail_not_pass(self):
        record = self.record(session_cat(), check_spec_run())
        self.assertEqual(record['subagent_cat'], 'absent')
        self.assertEqual(record['result'], 'fail')

    def test_no_session_cat_is_fail(self):
        record = self.record(subagent_cat(), check_spec_run())
        self.assertEqual(record['session_cat'], 'absent')
        self.assertEqual(record['result'], 'fail')

    def test_no_check_spec_call_is_fail(self):
        record = self.record(session_cat(), subagent_cat())
        self.assertEqual(record['check_spec'], 'absent')
        self.assertEqual(record['result'], 'fail')

    def test_a_subagent_cat_does_not_count_as_the_session_cat(self):
        record = self.record(subagent_cat(), subagent_cat(), check_spec_run())
        self.assertEqual(record['session_cat'], 'absent')

    def test_a_cat_of_another_path_does_not_count_as_a_refusal(self):
        elsewhere = [call('s1', 'cat /var/www/html/personal/harness/claude/evals/nothing.md'), reply('s1', REFUSED, True)]
        record = self.record(elsewhere, subagent_cat(), check_spec_run())
        self.assertEqual(record['session_cat'], 'absent')
        self.assertEqual(record['result'], 'fail')

    def test_a_cat_that_succeeded_without_the_marker_is_unclear_and_fail(self):
        record = self.record(session_cat('some other text', is_error=False), subagent_cat(), check_spec_run())
        self.assertEqual(record['session_cat'], 'unclear')
        self.assertEqual(record['result'], 'fail')

    def test_one_read_among_refused_cats_is_a_read(self):
        extra = [call('s2', f'cat {TICKET}'), reply('s2', f'# {MARKER}', False)]
        record = self.record(session_cat(), extra, subagent_cat(), check_spec_run())
        self.assertEqual(record['session_cat'], 'read')

    def test_a_check_spec_call_with_an_error_and_no_result_line_is_not_a_run(self):
        record = self.record(session_cat(), subagent_cat(), check_spec_run('Traceback ...', is_error=True))
        self.assertEqual(record['check_spec'], 'refused')

    def test_a_check_spec_that_reports_failures_still_ran(self):
        record = self.record(session_cat(), subagent_cat(),
                             check_spec_run('FAIL x:3  bad\ncheck-spec: 1 failure(s), 0 warning(s)', is_error=True))
        self.assertEqual(record['check_spec'], 'ran')
        self.assertEqual(record['result'], 'pass')

    def test_an_empty_trace_is_fail(self):
        self.assertEqual(self.record([])['result'], 'fail')

    def test_a_line_that_is_not_json_is_skipped(self):
        path = trace_file(self.tmp.name, session_cat() + subagent_cat() + check_spec_run())
        path.write_text('not json\n' + path.read_text())
        self.assertEqual(probe.parse_record(path, TICKET, MARKER)['result'], 'pass')

    def test_a_tool_result_whose_content_is_a_list_of_text_blocks(self):
        listed = [call('s1', f'cat {TICKET}'),
                  reply('s1', [{'type': 'text', 'text': REFUSED}], True)]
        self.assertEqual(self.record(listed, subagent_cat(), check_spec_run())['session_cat'], 'refused')


class RecordLine(unittest.TestCase):
    def test_the_line_names_the_result_the_date_and_the_version(self):
        line = probe.record_line('pass', '2026-11-25', '2.1.331')
        self.assertEqual(line, 'Bash sandbox probe: pass (2026-11-25, Claude Code 2.1.331)')

    def test_the_driver_reads_pass_from_a_readme(self):
        readme = 'text\nBash sandbox probe: pass (2026-11-25, Claude Code 2.1.331)\nmore\n'
        self.assertEqual(probe.read_result(readme), 'pass')

    def test_the_driver_reads_fail_from_a_readme(self):
        self.assertEqual(probe.read_result('Bash sandbox probe: fail (2026-11-25, Claude Code 2.1.331)\n'), 'fail')

    def test_a_readme_with_no_record_reads_as_none(self):
        self.assertIsNone(probe.read_result('nothing here\n'))


if __name__ == '__main__':
    unittest.main()
