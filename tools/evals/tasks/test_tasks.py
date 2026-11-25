#!/usr/bin/env python3
"""The Bash-sandbox probe: its written deny paths and its record parser.
`claude` is never invoked. Runs in CI."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import probe_sandbox as probe
import run

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


FIXTURES = Path(__file__).resolve().parent / 'fixtures'


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Replay:
    """Stands in for `sandbox.run_session`: each call plays the next fixture
    (a synthetic stage output) instead of starting `claude`. It writes the files
    the fixture lists into the project, as the stage would, and keeps the
    command line the driver built."""

    def __init__(self, names, clock=None):
        self.steps = [json.loads((FIXTURES / f'{name}.json').read_text()) for name in names]
        self.clock = clock or Clock()
        self.calls = []

    def __call__(self, args, cwd, trace=None, timeout=None):
        if not self.steps:
            raise AssertionError(f'the driver started an unexpected session: {args[2]}')
        step = self.steps.pop(0)
        resume = args[args.index('--resume') + 1] if '--resume' in args else None
        self.calls.append({'prompt': args[2], 'resume': resume, 'args': args, 'timeout': timeout})
        if step.get('raise') == 'timeout':
            raise subprocess.TimeoutExpired(args, timeout)
        self.clock.now += step.get('advance', 0)
        for rel, content in step.get('writes', {}).items():
            (Path(cwd) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(cwd) / rel).write_text(content)
        event = {'type': 'result', 'result': step.get('result', ''), 'is_error': step.get('is_error', False),
                 'session_id': resume or f's{len(self.calls)}', 'total_cost_usd': 0.1, 'num_turns': 2,
                 'duration_ms': 1000}
        Path(trace).write_text('\n'.join(json.dumps(e) for e in [*step.get('trace', []), event]) + '\n')
        return event


HAPPY_TO_REVIEW = ['spec_draft', 'spec_approved', 'plan_draft', 'plan_approved', 'build_complete', 'test_pass']


class DriverCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / 'project'
        self.project.mkdir()
        self.out = Path(self.tmp.name) / 'out'
        self.out.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def trial(self, names, clock=None, **options):
        replay = Replay(names, clock)
        record = run.run_trial(self.project, self.out, runner=replay, clock=replay.clock, **options)
        return record, replay

    def prompts(self, replay):
        return [call['prompt'] for call in replay.calls]


class ApprovalTurn(DriverCase):
    """REQ-018: the owner turn follows a draft, in that session, and only then."""

    def test_the_spec_approval_turn_is_sent_in_the_session_that_presented_the_draft(self):
        _, replay = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        self.assertEqual(replay.calls[0]['prompt'], '/spec ADD-1')
        self.assertEqual(replay.calls[1]['prompt'], 'I read the whole spec. I approve it.')
        self.assertEqual(replay.calls[1]['resume'], 's1')

    def test_the_plan_approval_turn_is_sent_in_the_session_that_presented_the_draft(self):
        _, replay = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        self.assertEqual(replay.calls[2]['prompt'], '/plan ADD-1')
        self.assertEqual(replay.calls[3]['prompt'], 'I read the whole plan. I approve it.')
        self.assertEqual(replay.calls[3]['resume'], 's3')

    def test_the_spec_header_reads_approved_after_the_turn(self):
        self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        self.assertIn('Status: Approved', (self.project / 'docs/specs/ADD-1-SPEC.md').read_text())

    def test_a_turn_that_leaves_the_spec_a_draft_stops_the_trial(self):
        record, replay = self.trial(['spec_draft', 'noop'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('not_approved', 'spec'))
        self.assertEqual(len(replay.calls), 2)

    def test_a_turn_that_leaves_the_plan_a_draft_stops_the_trial(self):
        record, _ = self.trial(['spec_draft', 'spec_approved', 'plan_draft', 'noop'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('not_approved', 'plan'))

    def test_no_turn_sent_before_a_draft_exists_contains_approve(self):
        _, replay = self.trial([*HAPPY_TO_REVIEW, 'review_required', 'build_complete', 'test_pass', 'review_clean'])
        first_turns = [call['prompt'] for call in replay.calls if call['resume'] is None]
        self.assertGreaterEqual(len(first_turns), 5)
        for prompt in first_turns:
            self.assertNotIn('approv', prompt.lower())

    def test_the_stage_prompts_hold_no_approval_text(self):
        for stage, prompt in run.STAGE_PROMPT.items():
            self.assertNotIn('approv', prompt.lower(), stage)

    def test_only_the_two_approval_turns_resume_a_session_in_a_clean_run(self):
        _, replay = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        resumed = [call['prompt'] for call in replay.calls if call['resume']]
        self.assertEqual(resumed, ['I read the whole spec. I approve it.', 'I read the whole plan. I approve it.'])

    def test_the_stages_run_in_order(self):
        _, replay = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        self.assertEqual([p for p in self.prompts(replay) if p.startswith('/')],
                         ['/spec ADD-1', '/plan ADD-1', '/build ADD-1', '/test ADD-1', '/review ADD-1'])

    def test_a_spec_that_is_already_approved_gets_no_approval_turn(self):
        record, replay = self.trial(['spec_approved', 'plan_approved', 'build_complete', 'test_pass', 'review_clean'])
        self.assertEqual(self.prompts(replay), ['/spec ADD-1', '/plan ADD-1', '/build ADD-1', '/test ADD-1', '/review ADD-1'])
        self.assertEqual(record['stop_reason'], 'complete')


class FixRound(DriverCase):
    """REQ-018: REQUIRED or BLOCKER findings get one fix round, as `/review` routes it."""

    FIX = ['build_complete', 'test_pass', 'review_clean']

    def test_required_findings_run_one_fix_round(self):
        record, replay = self.trial([*HAPPY_TO_REVIEW, 'review_required', *self.FIX])
        self.assertEqual(self.prompts(replay)[-3:], ['/build ADD-1 review fixes', '/test ADD-1', '/review ADD-1'])
        self.assertTrue(record['fix_round'])
        self.assertEqual(record['stop_reason'], 'complete')

    def test_a_blocker_alone_runs_the_fix_round(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW, 'review_blocker', *self.FIX])
        self.assertTrue(record['fix_round'])

    def test_advisory_findings_alone_run_no_fix_round(self):
        record, replay = self.trial([*HAPPY_TO_REVIEW, 'review_advisory'])
        self.assertFalse(record['fix_round'])
        self.assertEqual(len(replay.calls), 7)

    def test_a_clean_review_runs_no_fix_round(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        self.assertFalse(record['fix_round'])

    def test_findings_left_after_the_fix_round_start_no_second_round(self):
        record, replay = self.trial([*HAPPY_TO_REVIEW, 'review_required', 'build_complete', 'test_pass', 'review_required'])
        self.assertEqual(self.prompts(replay).count('/build ADD-1 review fixes'), 1)
        self.assertEqual(record['stop_reason'], 'complete')
        self.assertEqual(len(replay.calls), 10)

    def test_a_blocked_fix_build_stops_before_test_and_review(self):
        record, replay = self.trial([*HAPPY_TO_REVIEW, 'review_required', 'build_blocked'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('blocked', 'build'))
        self.assertEqual(len(replay.calls), 8)


class StopRules(DriverCase):
    """REQ-019: the driver stops, and the record holds the reason and the stage."""

    def test_a_blocked_stage_stops_the_trial_and_no_later_stage_runs(self):
        record, replay = self.trial([*HAPPY_TO_REVIEW[:4], 'build_blocked'])
        self.assertEqual((record['stop_reason'], record['stop_stage'], record['last_stage']), ('blocked', 'build', 'build'))
        self.assertIn('BUILD BLOCKED', record['stop_detail'])
        self.assertEqual(len(replay.calls), 5)

    def test_a_blocked_verification_stops_at_test(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW[:5], 'test_blocked'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('blocked', 'test'))

    def test_a_blocked_review_stops_at_review(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW, 'review_blocked'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('blocked', 'review'))

    def test_a_question_before_the_spec_draft_stops_at_spec(self):
        record, replay = self.trial(['spec_question'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'spec'))
        self.assertEqual(len(replay.calls), 1)

    def test_a_spec_conflict_from_plan_stops_at_plan(self):
        record, replay = self.trial(['spec_draft', 'spec_approved', 'plan_conflict'])
        self.assertEqual((record['stop_reason'], record['stop_stage'], record['last_stage']), ('question', 'plan', 'plan'))
        self.assertIn('SPEC CONFLICT', record['stop_detail'])
        self.assertEqual(len(replay.calls), 3)

    def test_a_build_that_ends_without_its_report_is_a_question(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW[:4], 'build_unfinished'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'build'))

    def test_a_stage_that_runs_past_its_time_limit_stops_with_reason_time(self):
        record, replay = self.trial([*HAPPY_TO_REVIEW[:4], 'timeout'])
        self.assertEqual((record['stop_reason'], record['stop_stage'], record['stop_detail']), ('time', 'build', 'stage'))
        self.assertEqual(replay.calls[-1]['timeout'], run.STAGE_LIMIT['build'])

    def test_every_stage_has_a_limit_inside_the_wall_limit(self):
        self.assertEqual(set(run.STAGE_LIMIT), {'spec', 'plan', 'build', 'test', 'review'})
        self.assertEqual(run.WALL_LIMIT, 90 * 60)
        self.assertTrue(all(0 < limit <= run.WALL_LIMIT for limit in run.STAGE_LIMIT.values()))

    def test_a_session_gets_only_the_wall_time_left(self):
        clock = Clock()
        _, replay = self.trial([*HAPPY_TO_REVIEW[:4], 'build_slow', 'timeout'], clock)
        self.assertEqual(replay.calls[-1]['prompt'], '/test ADD-1')
        self.assertEqual(replay.calls[-1]['timeout'], run.WALL_LIMIT - 5000)

    def test_a_session_that_runs_out_the_wall_time_stops_with_reason_time(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW[:4], 'build_slow', 'timeout'], Clock())
        self.assertEqual((record['stop_reason'], record['stop_stage'], record['stop_detail']), ('time', 'test', 'wall'))

    def test_no_session_starts_after_the_wall_time_is_spent(self):
        record, replay = self.trial([*HAPPY_TO_REVIEW[:4], 'build_wall'])
        self.assertEqual((record['stop_reason'], record['stop_stage'], record['stop_detail']), ('time', 'test', 'wall'))
        self.assertEqual(len(replay.calls), 5)

    def test_a_session_that_fails_stops_with_reason_error(self):
        def failing(args, cwd, trace=None, timeout=None):
            raise RuntimeError('claude exited 1: boom')
        record = run.run_trial(self.project, self.out, runner=failing, clock=Clock())
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('error', 'spec'))
        self.assertIn('boom', record['stop_detail'])

    def test_a_result_event_that_reports_an_error_stops_with_reason_error(self):
        def errored(args, cwd, trace=None, timeout=None):
            Path(trace).write_text('')
            return {'is_error': True, 'subtype': 'error_max_budget_usd', 'session_id': 's1', 'total_cost_usd': 5}
        record = run.run_trial(self.project, self.out, runner=errored, clock=Clock())
        self.assertEqual(record['stop_reason'], 'error')
        self.assertIn('error_max_budget_usd', record['stop_detail'])

    def test_a_clean_run_stops_with_reason_complete_at_review(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        self.assertEqual((record['stop_reason'], record['stop_stage'], record['last_stage']), ('complete', None, 'review'))


class Budget(DriverCase):
    def test_a_session_gets_the_smaller_of_its_cap_and_the_budget_left(self):
        _, replay = self.trial([*HAPPY_TO_REVIEW[:2], 'timeout'], session_budget=10, trial_budget=10.15)
        caps = [call['args'][call['args'].index('--max-budget-usd') + 1] for call in replay.calls]
        self.assertEqual(caps, ['10', '10', '9.95'])

    def test_the_trial_stops_when_its_budget_is_spent(self):
        record, replay = self.trial(HAPPY_TO_REVIEW, session_budget=1, trial_budget=0.2)
        self.assertEqual(record['stop_reason'], 'error')
        self.assertIn('budget', record['stop_detail'])
        self.assertEqual(len(replay.calls), 2)

    def test_the_record_sums_the_cost_of_every_turn(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        self.assertAlmostEqual(record['cost_usd'], 0.7)
        self.assertEqual(len(record['turns']), 7)


class SessionShape(DriverCase):
    def test_no_session_gets_add_dir(self):
        _, replay = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        for call in replay.calls:
            self.assertNotIn('--add-dir', call['args'])

    def test_the_stage_sessions_may_run_bash(self):
        _, replay = self.trial(['spec_question'])
        self.assertIn('Bash', replay.calls[0]['args'])

    def test_every_stage_starts_a_fresh_session(self):
        _, replay = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        firsts = [call for call in replay.calls if call['prompt'].startswith('/')]
        self.assertTrue(all(call['resume'] is None for call in firsts))


class LeakAudit(DriverCase):
    def test_a_stage_that_names_the_hidden_files_is_recorded_as_leaked(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW[:4], 'build_leak', 'test_pass', 'review_clean'])
        self.assertTrue(record['leaked'])
        self.assertEqual(len(record['leaks']), 1)
        self.assertIn('hidden/checks.json', record['leaks'][0]['text'])

    def test_a_clean_run_is_not_leaked(self):
        record, _ = self.trial([*HAPPY_TO_REVIEW, 'review_clean'])
        self.assertFalse(record['leaked'])


README_PASS = 'Bash sandbox probe: pass (2026-12-01, Claude Code 9.9.9)\n'
README_FAIL = 'Bash sandbox probe: fail (2026-11-25, Claude Code 2.1.331)\n'


class Prevention(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.harness = tmp / 'repo' / 'claude'
        for name in ('commands', 'evals/add-business'):
            (self.harness / name).mkdir(parents=True)
        (self.harness / 'AGENTS.md').write_text('rules\n')
        (self.harness / 'settings.json').write_text(json.dumps({'model': 'opus', 'env': {}}))
        self.project = tmp / 'project'
        self.project.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def settings(self):
        return json.loads((self.project / '.claude/settings.local.json').read_text())

    def test_the_sandbox_setting_is_written_when_the_probe_passed(self):
        self.assertTrue(run.prepare(self.project, README_PASS, self.harness))
        deny = self.settings()['sandbox']['filesystem']['denyRead']
        self.assertEqual(deny, [str((self.harness / 'evals').resolve())])

    def test_the_sandbox_setting_is_not_written_when_the_probe_failed(self):
        self.assertFalse(run.prepare(self.project, README_FAIL, self.harness))
        self.assertNotIn('sandbox', self.settings())

    def test_the_sandbox_setting_is_not_written_when_there_is_no_probe_record(self):
        self.assertFalse(run.prepare(self.project, 'nothing here\n', self.harness))
        self.assertNotIn('sandbox', self.settings())

    def test_the_harness_copy_stays_out_of_the_projects_git_status(self):
        run.prepare(self.project, README_FAIL, self.harness)
        status = subprocess.run(['git', '-C', str(self.project), 'status', '--short'],
                                capture_output=True, text=True, check=True).stdout
        self.assertEqual(status, '')

    def test_a_report_without_prevention_starts_with_the_detection_only_line(self):
        text = run.render_report({'prevention': False, 'stop_reason': 'complete', 'leaked': False, 'leaks': [],
                                  'turns': [], 'cost_usd': 0, 'last_stage': 'review'})
        self.assertEqual(text.splitlines()[0], 'prevention off: detection only')

    def test_a_report_with_prevention_does_not_say_detection_only(self):
        text = run.render_report({'prevention': True, 'stop_reason': 'complete', 'leaked': False, 'leaks': [],
                                  'turns': [], 'cost_usd': 0, 'last_stage': 'review'})
        self.assertNotIn('detection only', text)

    def test_the_report_names_the_stop_reason_and_stage(self):
        text = run.render_report({'prevention': False, 'stop_reason': 'question', 'stop_stage': 'plan',
                                  'stop_detail': 'SPEC CONFLICT', 'leaked': True,
                                  'leaks': [{'tool': 'Bash', 'text': 'cat x', 'subagent': False}],
                                  'turns': [], 'cost_usd': 1.5, 'last_stage': 'plan'})
        self.assertIn('question at /plan', text)
        self.assertIn('LEAKED', text)


class SetupTrial(unittest.TestCase):
    def test_setup_sh_makes_a_git_project_with_the_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'trial'
            run.setup_trial(dest)
            self.assertTrue((dest / 'docs/specs/ADD-1-intake.md').is_file())
            self.assertTrue((dest / '.git').is_dir())
            self.assertFalse((dest / 'hidden').exists())


if __name__ == '__main__':
    unittest.main()
