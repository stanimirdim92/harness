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

import core
import eval as eval_cli
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
        self.session_cost = {}

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
        session = resume or f's{len(self.calls)}'
        self.session_cost[session] = self.session_cost.get(session, 0) + 0.1
        event = {'type': 'result', 'result': step.get('result', ''), 'is_error': step.get('is_error', False),
                 'session_id': session, 'total_cost_usd': self.session_cost[session], 'num_turns': 2,
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


class OpenQuestion(DriverCase):
    """REQ-019: a Draft that holds an OPEN QUESTION asks the owner something other than the approval."""

    def test_a_spec_draft_with_an_open_question_stops_with_reason_question_and_no_approval_turn(self):
        record, replay = self.trial(['spec_draft_open_question'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'spec'))
        self.assertIn('OPEN QUESTION', record['stop_detail'])
        self.assertEqual(len(replay.calls), 1)

    def test_a_plan_draft_with_an_open_question_stops_with_reason_question(self):
        record, replay = self.trial(['spec_draft', 'spec_approved', 'plan_draft_open_question'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'plan'))
        self.assertEqual(len(replay.calls), 3)

    def test_a_line_that_only_mentions_an_open_question_is_not_one(self):
        record, replay = self.trial(['spec_draft_mentions_open_question', 'spec_approved', 'timeout'])
        self.assertEqual(replay.calls[1]['prompt'], 'I read the whole spec. I approve it.')
        self.assertNotEqual(record['stop_reason'], 'question')

    def test_a_spec_draft_where_one_block_marks_no_option_recommended_gets_no_turn_and_stops(self):
        record, replay = self.trial(['spec_draft_one_unmarked'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'spec'))
        self.assertIn('Q2', record['stop_detail'])
        self.assertEqual(self.prompts(replay), ['/spec ADD-1'])

    def test_a_block_that_marks_two_options_recommended_gets_no_turn_and_stops(self):
        record, replay = self.trial(['spec_draft_two_recommended'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'spec'))
        self.assertEqual(self.prompts(replay), ['/spec ADD-1'])

    def test_a_plan_draft_that_marks_no_option_recommended_gets_no_turn_and_stops(self):
        record, replay = self.trial(['spec_draft', 'spec_approved', 'plan_draft_open_question'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'plan'))
        self.assertEqual(self.prompts(replay)[-1], '/plan ADD-1')


class DecisionTurn(DriverCase):
    """REQ-018, DEC-013: open questions that all carry one recommended option get one decision turn, then the approval."""

    DECISION = 'For every open question, take the recommended option.'

    def test_the_spec_decision_turn_then_the_approval_turn_run_in_the_session_that_presented_the_draft(self):
        _, replay = self.trial(['spec_draft_recommended', 'spec_decided', 'spec_approved', 'timeout'])
        self.assertEqual(self.prompts(replay)[:3],
                         ['/spec ADD-1', self.DECISION, 'I read the whole spec. I approve it.'])
        self.assertEqual([call['resume'] for call in replay.calls[:3]], [None, 's1', 's1'])

    def test_the_spec_header_reads_approved_after_the_decision_and_approval_turns(self):
        self.trial(['spec_draft_recommended', 'spec_decided', 'spec_approved', 'timeout'])
        self.assertIn('Status: Approved', (self.project / 'docs/specs/ADD-1-SPEC.md').read_text())

    def test_the_plan_decision_turn_then_the_approval_turn_run_in_the_session_that_presented_the_draft(self):
        _, replay = self.trial(['spec_draft', 'spec_approved', 'plan_draft_recommended', 'plan_decided',
                                'plan_approved', 'timeout'])
        self.assertEqual(self.prompts(replay)[2:5],
                         ['/plan ADD-1', self.DECISION, 'I read the whole plan. I approve it.'])
        self.assertEqual([call['resume'] for call in replay.calls[2:5]], [None, 's3', 's3'])

    def test_the_trial_goes_on_to_build_after_both_decision_turns(self):
        record, replay = self.trial(['spec_draft_recommended', 'spec_decided', 'spec_approved',
                                     'plan_draft_recommended', 'plan_decided', 'plan_approved',
                                     'build_complete', 'test_pass', 'review_clean'])
        self.assertEqual(record['stop_reason'], 'complete')
        self.assertEqual(record['stop_stage'], None)
        self.assertEqual([p for p in self.prompts(replay) if p == self.DECISION], [self.DECISION] * 2)

    def test_a_spec_that_still_holds_an_open_question_after_the_decision_turn_stops_with_no_second_decision(self):
        record, replay = self.trial(['spec_draft_recommended', 'spec_draft_recommended'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'spec'))
        self.assertIn('OPEN QUESTION', record['stop_detail'])
        self.assertEqual(self.prompts(replay), ['/spec ADD-1', self.DECISION])

    def test_a_plan_that_still_holds_an_open_question_after_the_decision_turn_stops_with_no_second_decision(self):
        record, replay = self.trial(['spec_draft', 'spec_approved', 'plan_draft_recommended',
                                     'plan_draft_recommended'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('question', 'plan'))
        self.assertEqual(self.prompts(replay)[2:], ['/plan ADD-1', self.DECISION])

    def test_a_decision_turn_that_leaves_the_draft_unapproved_after_the_approval_turn_stops_not_approved(self):
        record, _ = self.trial(['spec_draft_recommended', 'spec_decided', 'noop'])
        self.assertEqual((record['stop_reason'], record['stop_stage']), ('not_approved', 'spec'))

    def test_a_decision_turn_that_leaves_an_approved_spec_gets_no_approval_turn(self):
        _, replay = self.trial(['spec_draft_recommended', 'spec_approved', 'plan_approved', 'timeout'])
        self.assertEqual(self.prompts(replay)[:3], ['/spec ADD-1', self.DECISION, '/plan ADD-1'])

    def test_no_turn_sent_before_a_draft_exists_names_the_recommended_option(self):
        _, replay = self.trial(['spec_draft_recommended', 'spec_decided', 'spec_approved',
                                'plan_draft_recommended', 'plan_decided', 'plan_approved',
                                'build_complete', 'test_pass', 'review_clean'])
        first_turns = [call['prompt'] for call in replay.calls if call['resume'] is None]
        self.assertEqual(len(first_turns), 5)
        for prompt in first_turns:
            self.assertNotIn('recommended option', prompt.lower())
        for stage, prompt in run.STAGE_PROMPT.items():
            self.assertNotIn('recommended', prompt.lower(), stage)

    def test_the_decision_turn_holds_no_approval_text(self):
        self.assertNotIn('approv', run.DECISION.lower())


class SessionCost(DriverCase):
    """A resumed session reports the cost of the whole session so far. The trial cost counts each turn once."""

    def test_the_approval_turn_adds_only_what_it_cost_on_top_of_the_draft_turn(self):
        record, _ = self.trial(['spec_draft', 'spec_approved', 'timeout'])
        self.assertAlmostEqual(record['turns'][0]['cost_usd'], 0.1)
        self.assertAlmostEqual(record['turns'][1]['cost_usd'], 0.1)
        self.assertAlmostEqual(record['cost_usd'], 0.2)

    def test_a_resumed_session_may_spend_up_to_the_session_cap_in_all(self):
        _, replay = self.trial(['spec_draft', 'spec_approved', 'timeout'], session_budget=1, trial_budget=0.25)
        caps = [call['args'][call['args'].index('--max-budget-usd') + 1] for call in replay.calls]
        self.assertEqual(caps, ['0.25', '0.25', '0.05'])


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


def fake_grader(folder, fixture, exit_code=1, stdout=None):
    """A shell script that prints a recorded `grade.sh` JSON, so grading needs no PHP."""
    script = Path(folder) / 'grade.sh'
    body = stdout if stdout is not None else (FIXTURES / f'{fixture}.json').read_text()
    (Path(folder) / 'grade-output.json').write_text(body)
    script.write_text(f'#!/bin/sh\ncat "$(dirname "$0")/grade-output.json"\necho "grade note" >&2\nexit {exit_code}\n')
    script.chmod(0o755)
    return script


def graded(fixture='grade_two_failed'):
    return json.loads((FIXTURES / f'{fixture}.json').read_text())


def driver_record(**fields):
    return {'prevention': False, 'leaked': False, 'leaks': [], 'cost_usd': 1.5, 'wall_s': 12.0, 'last_stage': 'review',
            'stop_reason': 'complete', 'stop_stage': None, 'stop_detail': '', 'fix_round': False, 'turns': [], **fields}


class Grade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_grade_json_is_stored_in_the_trial_folder(self):
        out = self.dir / 'out'
        out.mkdir()
        doc = run.grade(self.dir, out, fake_grader(self.dir, 'grade_two_failed'))
        self.assertEqual(doc['passed'], 4)
        self.assertEqual(json.loads((out / 'grade.json').read_text()), graded())

    def test_a_grader_that_exits_0_is_read(self):
        out = self.dir / 'out'
        out.mkdir()
        doc = run.grade(self.dir, out, fake_grader(self.dir, 'grade_all_pass', exit_code=0))
        self.assertTrue(doc['pass'])

    def test_a_grader_that_cannot_run_raises_with_its_message(self):
        out = self.dir / 'out'
        out.mkdir()
        grader = fake_grader(self.dir, 'grade_two_failed', exit_code=2, stdout='')
        with self.assertRaisesRegex(RuntimeError, r'grade.sh exited 2.*grade note'):
            run.grade(self.dir, out, grader)

    def test_output_that_is_not_a_grade_raises(self):
        out = self.dir / 'out'
        out.mkdir()
        with self.assertRaisesRegex(RuntimeError, 'no checks'):
            run.grade(self.dir, out, fake_grader(self.dir, 'x', stdout='{"passed": 3}'))

    def test_the_trial_holds_checks_passed_of_total_and_the_failed_ids(self):
        trial = run.trial_record(driver_record(), graded())
        self.assertEqual((trial['passed'], trial['total']), (4, 6))
        self.assertEqual(trial['failed'], ['API-01', 'UI-01'])
        self.assertEqual(trial['checks']['API-01'], False)
        self.assertEqual(trial['checks']['BASE-1'], True)

    def test_the_trial_holds_the_stop_reason_the_stage_and_the_leak_flag(self):
        trial = run.trial_record(driver_record(stop_reason='question', stop_stage='plan', last_stage='plan'), graded())
        self.assertEqual((trial['stop_reason'], trial['stop_stage'], trial['last_stage']), ('question', 'plan', 'plan'))
        self.assertIs(trial['leaked'], False)

    def test_the_trial_carries_the_cost_and_the_duration(self):
        trial = run.trial_record(driver_record(), graded())
        self.assertEqual((trial['cost_usd'], trial['duration_ms']), (1.5, 12000))

    def test_a_leaked_trial_fails_every_check(self):
        leak = [{'tool': 'Bash', 'text': 'cat /x/claude/evals/add-business/hidden/a', 'subagent': True}]
        trial = run.trial_record(driver_record(leaked=True, leaks=leak), graded('grade_all_pass'))
        self.assertFalse(any(trial['checks'].values()))
        self.assertEqual((trial['passed'], trial['total']), (0, 6))
        self.assertEqual(trial['grade_passed'], 6)
        self.assertEqual(run.TasksSuite.state(None, trial), 'fail')

    def test_a_trial_that_passes_every_check_is_pass(self):
        trial = run.trial_record(driver_record(), graded('grade_all_pass'))
        self.assertEqual(run.TasksSuite.state(None, trial), 'pass')

    def test_a_trial_with_one_failed_check_is_fail(self):
        trial = run.trial_record(driver_record(), graded())
        self.assertEqual(run.TasksSuite.state(None, trial), 'fail')

    def test_a_trial_with_no_checks_is_errored(self):
        self.assertEqual(run.TasksSuite.state(None, {'checks': None}), 'errored')
        self.assertEqual(run.TasksSuite.state(None, {}), 'errored')


class Preflight(unittest.TestCase):
    @staticmethod
    def ok(code):
        return lambda *a, **k: subprocess.CompletedProcess(a, code)

    def test_a_missing_tool_is_named(self):
        problem = run.grader_problem(which=lambda tool: None if tool == 'node' else '/bin/' + tool, run=self.ok(0))
        self.assertIn('node', problem)

    def test_php_without_pdo_sqlite_is_named(self):
        problem = run.grader_problem(which=lambda tool: '/bin/' + tool, run=self.ok(1))
        self.assertIn('pdo_sqlite', problem)

    def test_nothing_is_wrong_when_the_tools_and_the_driver_are_there(self):
        self.assertIsNone(run.grader_problem(which=lambda tool: '/bin/' + tool, run=self.ok(0)))


class SuiteTrial(unittest.TestCase):
    """One trial through `TasksSuite.run_trial`: the real `setup.sh`, a replayed `claude`, a recorded grade."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.harness = tmp / 'repo' / 'claude'
        (self.harness / 'commands').mkdir(parents=True)
        (self.harness / 'evals').mkdir()
        (self.harness / 'AGENTS.md').write_text('rules\n')
        (self.harness / 'settings.json').write_text(json.dumps({'model': 'opus', 'env': {}}))
        self.folder = tmp / 'results' / 'add-business' / 't1'
        self.folder.mkdir(parents=True)
        self.case = {'id': 'add-business', 'split': 'optimization', 'tags': []}
        self.grader = fake_grader(tmp, 'grade_two_failed')

    def tearDown(self):
        self.tmp.cleanup()

    def suite(self, names, readme=README_FAIL, **options):
        self.replay = Replay(names)
        return run.TasksSuite(runner=self.replay, grader=self.grader, readme_text=readme, harness=self.harness,
                              clock=self.replay.clock, preflight=lambda: None, **options)

    def test_a_trial_is_graded_and_holds_its_record(self):
        trial = self.suite([*HAPPY_TO_REVIEW, 'review_clean']).run_trial(self.case, self.folder)
        self.assertEqual((trial['passed'], trial['total']), (4, 6))
        self.assertEqual(trial['stop_reason'], 'complete')
        self.assertAlmostEqual(trial['cost_usd'], 0.7)
        self.assertTrue((self.folder / 'grade.json').is_file())
        self.assertTrue((self.folder / 'driver.json').is_file())

    def test_the_suite_hashes_the_installed_harness_it_runs(self):
        hashes = self.suite([]).instruction_hashes([self.case])
        self.assertEqual(sorted(hashes), ['AGENTS.md', 'settings.json'])
        (self.harness / 'AGENTS.md').write_text('other rules\n')
        changed = self.suite([]).instruction_hashes([self.case])
        self.assertEqual([k for k in hashes if hashes[k] != changed[k]], ['AGENTS.md'])

    def test_a_trial_that_stopped_early_is_still_graded(self):
        trial = self.suite(['spec_question']).run_trial(self.case, self.folder)
        self.assertEqual((trial['stop_reason'], trial['stop_stage']), ('question', 'spec'))
        self.assertEqual(trial['total'], 6)
        self.assertTrue((self.folder / 'grade.json').is_file())

    def test_the_specs_and_the_plan_the_stages_wrote_are_kept_with_the_trial(self):
        self.suite([*HAPPY_TO_REVIEW, 'review_clean']).run_trial(self.case, self.folder)
        self.assertIn('Status: Approved', (self.folder / 'artifacts/docs/specs/ADD-1-SPEC.md').read_text())

    def test_the_trial_says_whether_prevention_was_on(self):
        self.assertIs(self.suite(['spec_question']).run_trial(self.case, self.folder)['prevention'], False)

    def test_a_grader_that_cannot_run_makes_the_trial_raise(self):
        self.grader = fake_grader(self.tmp.name, 'x', exit_code=2, stdout='')
        with self.assertRaises(RuntimeError):
            self.suite(['spec_question']).run_trial(self.case, self.folder)

    def test_a_preflight_problem_raises_before_any_session_starts(self):
        suite = self.suite([])
        suite.preflight = lambda: 'php has no pdo_sqlite driver'
        with self.assertRaisesRegex(RuntimeError, 'pdo_sqlite'):
            suite.run_trial(self.case, self.folder)
        self.assertEqual(self.replay.calls, [])

    def test_a_retry_of_the_same_trial_gets_only_the_budget_the_first_attempt_left(self):
        suite = self.suite([*HAPPY_TO_REVIEW, 'review_clean', 'spec_question'], trial_budget=0.8)
        suite.run_trial(self.case, self.folder)
        suite.run_trial(self.case, self.folder)
        caps = [call['args'][call['args'].index('--max-budget-usd') + 1] for call in self.replay.calls]
        self.assertEqual(caps[-1], '0.1')

    def test_a_retry_with_no_budget_left_raises_and_starts_no_session(self):
        suite = self.suite([*HAPPY_TO_REVIEW, 'review_clean'], trial_budget=0.7)
        suite.run_trial(self.case, self.folder)
        calls = len(self.replay.calls)
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            suite.run_trial(self.case, self.folder)
        self.assertEqual(len(self.replay.calls), calls)


def trial(checks, state=None, **fields):
    record = {'n': 1, 'checks': checks, 'cost_usd': 1.0, 'duration_ms': 1000, 'retried': False, 'error': None,
              'folder': 'add-business/t1', 'prevention': False, 'leaked': False, 'stop_reason': 'complete',
              'stop_stage': None, **fields}
    record['state'] = state or ('pass' if all(checks.values()) else 'fail')
    return record


class CheckStates(unittest.TestCase):
    """REQ-020: a state per hidden check over the trials, and the trials that passed every check."""

    def result(self, *trials):
        return core.case_result('check', 'add-business', list(trials))

    def test_a_check_every_trial_passed_is_pass(self):
        result = self.result(trial({'A': True}), trial({'A': True}), trial({'A': True}))
        self.assertEqual(result['items']['A'], 'PASS')

    def test_a_check_some_trials_passed_is_flaky(self):
        result = self.result(trial({'A': True}), trial({'A': False}), trial({'A': True}))
        self.assertEqual(result['items']['A'], 'FLAKY')

    def test_a_check_no_trial_passed_is_fail(self):
        result = self.result(trial({'A': False}), trial({'A': False}))
        self.assertEqual(result['items']['A'], 'FAIL')

    def test_the_case_result_counts_the_trials_that_passed_every_check(self):
        result = self.result(trial({'A': True, 'B': True}), trial({'A': True, 'B': False}), trial({'A': True, 'B': True}))
        self.assertEqual((result['passed'], result['scored']), (2, 3))
        self.assertEqual(result['items'], {'A': 'PASS', 'B': 'FLAKY'})

    def test_an_errored_trial_is_not_scored(self):
        result = self.result(trial({'A': True}), trial({'A': None}, state='errored'))
        self.assertEqual(result['scored'], 1)

    def test_the_tasks_suite_items_are_checks_and_a_lost_check_is_not_a_lost_gate(self):
        suite = run.TasksSuite(preflight=lambda: None)
        self.assertEqual((suite.name, suite.kind, bool(getattr(suite, 'any_loss_is_worse', False))),
                         ('tasks', 'check', False))
        self.assertEqual(suite.all_cases(), [{'id': 'add-business', 'split': 'optimization', 'tags': []}])


def report_doc(trials, prevention=False):
    entries = [{'id': 'add-business', 'split': 'optimization', 'tags': [], 'semantic_review': 'pending',
                'result': core.case_result('check', 'add-business', trials), 'trials': trials}]
    return {'schema': 1, 'suite': 'tasks', 'run': '2026-11-25-120000-abc1234', 'item_kind': 'check',
            'harness_commit': 'abc1234', 'dirty': False, 'instruction_hashes': None, 'model': None,
            'trials': len(trials), 'started': '2026-11-25T12:00:00', 'duration_ms': 60000, 'cost_usd': 3.0,
            'trials_without_cost': 0, 'cases': entries}


class TasksReport(unittest.TestCase):
    def report(self, trials):
        trials = [{**t, 'prevention': t.get('prevention', False)} for t in trials]
        return core.render_report(report_doc(trials), 'tools/evals/results/tasks/run')

    def test_the_report_starts_with_prevention_off_when_a_trial_ran_without_it(self):
        text = self.report([trial({'A': True})])
        self.assertEqual(text.splitlines()[0], 'prevention off: detection only')

    def test_the_report_says_prevention_is_on_only_when_every_trial_had_it(self):
        text = self.report([trial({'A': True}, prevention=True), trial({'A': True}, prevention=True)])
        self.assertNotIn('detection only', text)
        self.assertTrue(text.splitlines()[0].startswith('prevention on'))

    def test_one_trial_without_prevention_makes_the_whole_report_say_detection_only(self):
        text = self.report([trial({'A': True}, prevention=True), trial({'A': True}, prevention=False)])
        self.assertEqual(text.splitlines()[0], 'prevention off: detection only')

    def test_the_report_says_three_trials_measure_consistency_and_one_change_is_no_proof(self):
        text = self.report([trial({'A': True})])
        self.assertIn('3 trials measure consistency', text)
        self.assertIn('A change of one trial is not proof of a gain', text)

    def test_the_report_gives_the_trials_that_passed_every_check_and_the_check_states(self):
        text = self.report([trial({'A': True, 'B': True, 'C': False}), trial({'A': True, 'B': False, 'C': False})])
        self.assertIn('Trials that passed every check: 0 of 2', text)
        self.assertIn('Checks: 1 PASS, 1 FLAKY, 1 FAIL', text)
        self.assertIn('Failed in every trial: C', text)

    def test_the_report_names_a_leaked_trial(self):
        text = self.report([trial({'A': False}, leaked=True, folder='add-business/t2')])
        self.assertIn('LEAKED (counted as a fail): tools/evals/results/tasks/run/add-business/t2', text)

    def test_the_report_gives_the_stop_reason_and_stage_of_a_trial_that_did_not_finish(self):
        text = self.report([trial({'A': False}, stop_reason='question', stop_stage='plan')])
        self.assertIn('add-business/t1 stopped: question at /plan', text)

    def test_a_finished_trial_is_not_listed_as_stopped(self):
        self.assertNotIn('stopped:', self.report([trial({'A': True})]))

    def test_other_suites_reports_are_unchanged(self):
        doc = report_doc([trial({'A': True})])
        doc['suite'] = 'gates'
        text = core.render_report(doc, 'x')
        self.assertTrue(text.startswith('# gates run'))
        self.assertNotIn('consistency', text)


class EntryPoint(unittest.TestCase):
    def test_eval_py_builds_the_tasks_suite(self):
        self.assertIsNotNone(eval_cli.SUITES['tasks']['build'])
        suite = eval_cli.build(eval_cli.SUITES, 'tasks')
        self.assertEqual(suite.name, 'tasks')
        self.assertEqual([c['id'] for c in suite.all_cases()], ['add-business'])

    def test_the_tasks_flags_are_the_gates_flags(self):
        args = eval_cli.parser_for(eval_cli.SUITES).parse_args(['tasks', '--trials', '1', '--case', 'add-business'])
        self.assertEqual((args.command, args.trials, args.case), ('tasks', 1, ['add-business']))

    def test_eval_py_runs_the_tasks_suite_through_the_core(self):
        seen = {}

        class Stub:
            name, kind = 'tasks', 'check'

            def all_cases(self):
                return [{'id': 'add-business', 'split': 'optimization', 'tags': []}]

        def fake_run(suite, cases, trials, jobs, root, selection):
            seen.update(suite=suite.name, cases=[c['id'] for c in cases], trials=trials, jobs=jobs)
            return 0

        suites = {**eval_cli.SUITES, 'tasks': {**eval_cli.SUITES['tasks'], 'build': Stub}}
        original, core.run = core.run, fake_run
        try:
            code = eval_cli.main(['tasks', '--trials', '1'], suites=suites)
        finally:
            core.run = original
        self.assertEqual((code, seen), (0, {'suite': 'tasks', 'cases': ['add-business'], 'trials': 1, 'jobs': 1}))


if __name__ == '__main__':
    unittest.main()
