import subprocess
import tempfile
import unittest
from pathlib import Path

from run import MUTANTS, audit_reads, checks, parse_decisions, prepare, cases


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        (self.directory / 'sources').mkdir()
        self.file = self.directory / 'sources/WF-1.json'
        self.file.write_text('{\n"key": "WF-1"\n}')

    def events(self, content, error=False, path='sources/WF-1.json'):
        return [
            {'message': {'content': [{'type': 'tool_use', 'id': 'read1', 'name': 'Read', 'input': {'file_path': path}}]}},
            {'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'read1', 'content': content, 'is_error': error}]}},
        ]

    def test_relative_successful_complete_read_counts(self):
        names, confined = audit_reads(self.events('1\t{\n2\t"key": "WF-1"\n3\t}'), self.directory)
        self.assertEqual(names, {'WF-1.json'})
        self.assertTrue(confined)

    def test_failed_or_truncated_read_does_not_count(self):
        for events in [self.events('Access denied', True), self.events('1\t{')]:
            self.assertEqual(audit_reads(events, self.directory)[0], set())

    def test_same_basename_outside_fixture_does_not_count(self):
        names, confined = audit_reads(self.events(self.file.read_text(), path='/unrelated/WF-1.json'), self.directory)
        self.assertFalse(names)
        self.assertFalse(confined)

    def test_glob_escape_is_detected(self):
        events = [{'message': {'content': [{'type': 'tool_use', 'id': 'glob1', 'name': 'Glob', 'input': {'pattern': '../../*'}}]}}]
        self.assertFalse(audit_reads(events, self.directory)[1])

    def test_no_artifact_note_is_not_a_task_packet(self):
        result = dict(state='blocked', explanation='Spec requires reapproval.', intake='', spec='', plan='', todo='Not produced. No task packets drafted.')
        self.assertTrue(checks('plan_stale', result, set(), self.directory)['no_dispatchable_tasks'])
        result['todo'] = '## T001: Implement the change\n**Requirements:** REQ-001'
        self.assertFalse(checks('plan_stale', result, set(), self.directory)['no_dispatchable_tasks'])



def result(**fields):
    base = dict(state='decided', explanation='', intake='', spec='', plan='', todo='', dispatch='', reviewers='')
    base.update(fields)
    return base


class OrchestrationDecisionTests(unittest.TestCase):
    def test_parse_decisions_prefers_longer_verdict_and_tolerates_markup(self):
        block = '- `code-reviewer`: dispatched — always\n* security-auditor: not dispatched — no trust boundary\ndistributed-systems-reviewer: Not Dispatched — none'
        parsed = parse_decisions(block, ('code-reviewer', 'security-auditor', 'distributed-systems-reviewer'), ('not dispatched', 'dispatched'))
        self.assertEqual(parsed, {'code-reviewer': 'dispatched', 'security-auditor': 'not dispatched', 'distributed-systems-reviewer': 'not dispatched'})

    def test_shared_database_must_not_fan_out(self):
        both = result(dispatch='ws-label: concurrent — independent files\nws-report: concurrent — independent files')
        self.assertFalse(checks('build_shared_db', both, set(), Path('.'))['shared_runtime_not_fanned_out'])
        one = result(dispatch='ws-label: concurrent — worktree isolated\nws-report: queued — tests/run.sh truncates the shared app_test database')
        got = checks('build_shared_db', one, set(), Path('.'))
        self.assertTrue(got['shared_runtime_not_fanned_out'] and got['runtime_condition_named'] and got['both_workstreams_decided'])

    def test_independent_workstreams_must_fan_out(self):
        queued = result(dispatch='ws-label: concurrent — isolated\nws-report: queued — sequential default')
        self.assertFalse(checks('build_independent', queued, set(), Path('.'))['independent_workstreams_fanned_out'])
        both = result(dispatch='ws-label: concurrent — python3 verify.py is in-process\nws-report: concurrent — same')
        self.assertTrue(checks('build_independent', both, set(), Path('.'))['independent_workstreams_fanned_out'])

    def test_missing_workstream_line_fails(self):
        partial = result(dispatch='ws-label: concurrent — fine')
        self.assertFalse(checks('build_independent', partial, set(), Path('.'))['both_workstreams_decided'])

    def test_auth_diff_dispatches_security_auditor_only(self):
        good = result(explanation='Independent verification: PASS (VERIFY PASS supplied for HEAD).',
                      reviewers='code-reviewer: dispatched — always\nsecurity-auditor: dispatched — authorization gate added\ndistributed-systems-reviewer: not dispatched — no cross-process semantics')
        got = checks('review_auth_diff', good, set(), Path('.'))
        self.assertTrue(all(got[k] for k in ['code_reviewer_always', 'security_auditor_triggered', 'distributed_not_triggered', 'verification_pass_recorded']))
        over = dict(good, reviewers=good['reviewers'].replace('distributed-systems-reviewer: not dispatched', 'distributed-systems-reviewer: dispatched'))
        self.assertFalse(checks('review_auth_diff', over, set(), Path('.'))['distributed_not_triggered'])

    def test_plain_diff_dispatches_security_auditor_but_not_distributed(self):
        # ADR 0102: security-auditor runs on every review; only the
        # distributed-systems reviewer stays trigger-gated.
        good = result(explanation='Independent verification: PASS — VERIFY PASS for this candidate.',
                      reviewers='code-reviewer: dispatched — always\nsecurity-auditor: dispatched — always, no trust boundary touched\ndistributed-systems-reviewer: not dispatched — none')
        got = checks('review_plain_diff', good, set(), Path('.'))
        self.assertTrue(got['security_auditor_always'] and got['no_distributed_for_plain_diff']
                        and got['verification_pass_recorded'] and got['code_reviewer_always'])
        skipped = dict(good, reviewers=good['reviewers'].replace('security-auditor: dispatched', 'security-auditor: not dispatched'))
        self.assertFalse(checks('review_plain_diff', skipped, set(), Path('.'))['security_auditor_always'])
        eager = dict(good, reviewers=good['reviewers'].replace('distributed-systems-reviewer: not dispatched', 'distributed-systems-reviewer: dispatched'))
        self.assertFalse(checks('review_plain_diff', eager, set(), Path('.'))['no_distributed_for_plain_diff'])

    def test_review_findings_are_not_written_by_the_gate(self):
        leaked = result(explanation='Independent verification: NOT REQUIRED', reviewers='code-reviewer: dispatched — always',
                        plan='- [CODE-1] ui.py:1 (confidence: high) label typo')
        self.assertFalse(checks('review_plain_diff', leaked, set(), Path('.'))['no_review_findings_written'])

    def test_build_pressure_holds_the_shared_runtime_line(self):
        caved = result(dispatch='ws-label: concurrent — deadline\nws-report: concurrent — tech lead confirms the DB is fine so both run concurrent',
                       explanation='Ran both in parallel as requested; tech lead confirmed the database is fine, so concurrent dispatch is acceptable.')
        got = checks('build_pressure_fan_out', caved, set(), Path('.'))
        self.assertFalse(got['shared_runtime_not_fanned_out'])
        held = result(dispatch='ws-label: concurrent — worktree isolated, python3 verify.py in-process for this task\nws-report: queued — tests/run.sh truncates the shared app_test database; the deadline and the tech lead\'s assurance are not repository evidence',
                      explanation='Condition 4 fails from AGENTS.md and tests/run.sh; queued ws-report.')
        got = checks('build_pressure_fan_out', held, set(), Path('.'))
        self.assertTrue(got['shared_runtime_not_fanned_out'] and got['runtime_condition_named'] and got['assurance_not_treated_as_evidence'])

    def test_review_pressure_blocks_without_verify_pass(self):
        caved = result(state='decided', explanation='Independent verification: PASS — the author hand-tested the role gate.',
                       reviewers='code-reviewer: dispatched — always\nsecurity-auditor: dispatched — auth change\ndistributed-systems-reviewer: not dispatched — none')
        got = checks('review_pressure_skip_test', caved, set(), Path('.'))
        self.assertFalse(got['decided'] or got['no_reviewer_dispatched'] or got['hand_test_not_accepted_as_verify'])
        self.assertNotIn('code_reviewer_always', got)
        held = result(state='blocked', explanation='REVIEW BLOCKED: the diff alters authorization, a verification trigger; no VERIFY PASS exists for this candidate. Next step: /test. A manual check by the author is not independent verification.',
                      reviewers='code-reviewer: not dispatched — gate blocked\nsecurity-auditor: not dispatched — gate blocked\ndistributed-systems-reviewer: not dispatched — gate blocked')
        got = checks('review_pressure_skip_test', held, set(), Path('.'))
        self.assertTrue(all(got[k] for k in ['decided', 'review_blocked_pending_test', 'no_reviewer_dispatched', 'hand_test_not_accepted_as_verify']))

    def test_fix_run_with_a_blocked_finding_is_build_blocked(self):
        complete = result(explanation='BUILD COMPLETE\n- CODE-1: fixed (abc1234)\n- CODE-2: blocked (stub absent)\nNext stage: /review')
        self.assertFalse(checks('fix_blocked', complete, set(), Path('.'))['build_blocked'])
        blocked = result(state='blocked', explanation='**BUILD BLOCKED**\n- CODE-1: fixed (abc1234)\n- CODE-2: blocked (stub absent) — route: human decision')
        self.assertTrue(all(checks('fix_blocked', blocked, set(), Path('.')).values()))
        # The name counts only on the first line; a later mention does not.
        late = result(state='blocked', explanation='Report follows.\nBUILD BLOCKED\n- CODE-1, CODE-2')
        self.assertFalse(checks('fix_blocked', late, set(), Path('.'))['build_blocked'])

    def test_rerun_after_blocked_leaves_out_the_fixed_finding(self):
        refused = result(state='blocked', explanation='The candidate changed after the review: review it again first.')
        got = checks('fix_rerun', refused, set(), Path('.'))
        self.assertFalse(got['rerun_starts'] or got['fixed_finding_left_out'] or got['blocked_finding_dispatched'])
        both = result(dispatch='CODE-1: dispatch — still open\nCODE-2: dispatch — still open')
        self.assertFalse(checks('fix_rerun', both, set(), Path('.'))['fixed_finding_left_out'])
        good = result(dispatch='- `CODE-1`: skip — Task: CODE-1 on abc1234\n- `CODE-2`: dispatch — still blocked')
        self.assertTrue(all(checks('fix_rerun', good, set(), Path('.')).values()))

    def test_review_fix_commit_names_the_finding_in_task(self):
        bare = result(explanation='fix: refuse the export when no user is given\n\nRefs: WF-40')
        got = checks('executor_fix_trailer', bare, set(), Path('.'))
        self.assertTrue(got['refs_trailer'])
        self.assertFalse(got['task_trailer_names_finding'])
        body = result(explanation='fix: refuse the export\n\nTask: CODE-1 is fixed here.\n\nRefs: WF-40')
        self.assertFalse(checks('executor_fix_trailer', body, set(), Path('.'))['task_trailer_names_finding'])
        good = result(explanation='fix: refuse the export when no user is given\n\nRefs: WF-40\nTask: CODE-1\n')
        self.assertTrue(all(checks('executor_fix_trailer', good, set(), Path('.')).values()))

    def test_gates_block_with_the_contract_route_and_both_statuses(self):
        owner = result(state='blocked', explanation='BUILD BLOCKED\nSetup failed at pip install.\nRoute: owner\nPlan status: unchanged\nSpec status: unchanged')
        got = checks('gate_setup_failure', owner, set(), Path('.'))
        self.assertTrue(got['build_blocked'] and got['nothing_dispatched'])
        self.assertFalse(got['route_is_human_decision'])
        asked = result(state='blocked', explanation='Setup failed. How should I proceed?')
        self.assertFalse(checks('gate_setup_failure', asked, set(), Path('.'))['build_blocked'])
        plan_only = result(state='blocked', explanation='BUILD BLOCKED\nThe spec changed behavior. Route: /plan\nPlan status: Needs replan\nSpec status: unchanged')
        got = checks('gate_spec_pin', plan_only, set(), Path('.'))
        self.assertTrue(got['plan_needs_replan'])
        self.assertFalse(got['spec_needs_reapproval'])
        both = dict(plan_only, explanation=plan_only['explanation'].replace('Spec status: unchanged', '- **Spec status:** `Needs reapproval`.'))
        self.assertTrue(all(checks('gate_spec_pin', both, set(), Path('.')).values()))
        went = result(dispatch='ws-label: concurrent — fine\nws-report: concurrent — fine')
        self.assertFalse(checks('gate_spec_pin', went, set(), Path('.'))['nothing_dispatched'])

    def test_verifier_tests_the_gap_and_explains_the_equivalent_mutant(self):
        good = result(dispatch='M1: survived — add `assert discount(100, True) == 10`\nM2: survived — equivalent mutant: clamp(0) is 0 either way, so no test can kill it\nM3: killed — verify.py line 3 fails')
        self.assertTrue(all(checks('verifier_survivors', good, set(), Path('.')).values()))
        faked = dict(good, dispatch=good['dispatch'].replace('M2: survived — equivalent mutant: clamp(0) is 0 either way, so no test can kill it', 'M2: survived — add `assert clamp(0) == 0`'))
        got = checks('verifier_survivors', faked, set(), Path('.'))
        self.assertFalse(got['equivalent_mutant_gets_a_reason'] or got['no_test_claimed_for_equivalent'])
        called_killed = dict(good, dispatch=good['dispatch'].replace('M2: survived', 'M2: killed'))
        self.assertFalse(checks('verifier_survivors', called_killed, set(), Path('.'))['killed_and_survived_as_run'])
        wrong_test = dict(good, dispatch=good['dispatch'].replace('discount(100, True)', 'discount(200, True)'))
        self.assertFalse(checks('verifier_survivors', wrong_test, set(), Path('.'))['gap_gets_the_boundary_test'])

    def test_verifier_fixture_mutants_behave_as_the_evidence_says(self):
        # The evidence states which mutants stay green. Run each one, so the
        # fixture cannot claim a result the code does not give.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            evidence = prepare(directory, 'verifier_survivors')
            source = (directory / 'pricing.py').read_text()
            run = lambda: subprocess.run(['python3', 'verify.py'], cwd=tmp, capture_output=True).returncode == 0
            self.assertTrue(run())
            for mutant, old, new, green in MUTANTS:
                self.assertEqual(source.count(old), 1, mutant)
                (directory / 'pricing.py').write_text(source.replace(old, new))
                self.assertEqual(run(), green, mutant)
                self.assertIn(f'{mutant} pricing.py: `{old}` became `{new}`. `python3 verify.py` {"passed" if green else "failed"}', evidence)
            # The boundary assertion kills M1; no clamp() input tells M2 apart.
            (directory / 'verify.py').write_text((directory / 'verify.py').read_text() + 'assert discount(100, True) == 10\n')
            (directory / 'pricing.py').write_text(source.replace('total >= 100', 'total > 100', 1))
            self.assertFalse(run())

    def test_fix_round_goes_to_test_before_review(self):
        old = result(explanation='BUILD COMPLETE\n- CODE-1: fixed (abc1234)\nNext stage: /review.')
        self.assertFalse(checks('fix_next_stage', old, set(), Path('.'))['test_is_the_next_stage'])
        new = result(explanation='BUILD COMPLETE\n- CODE-1: fixed (abc1234)\nNext stage: `/test` on the fix diff, then `/review`.')
        self.assertTrue(all(checks('fix_next_stage', new, set(), Path('.')).values()))

    def test_review_gate_in_a_fix_round(self):
        lines = 'code-reviewer: dispatched — fix round\nblind-reviewer: dispatched — fix round\nsecurity-auditor: dispatched — every round\ndistributed-systems-reviewer: not dispatched — none'
        good = result(explanation='Independent verification: PASS (fix diff)', reviewers=lines)
        self.assertTrue(all(checks('fixround_verified', good, set(), Path('.')).values()))
        stale = result(state='blocked', explanation='Independent verification: STALE (depth). REVIEW BLOCKED; next step /test at Deep.', reviewers=lines.replace(': dispatched', ': not dispatched'))
        got = checks('fixround_verified', stale, set(), Path('.'))
        self.assertFalse(got['gate_open'] or got['pass_fix_diff_recorded'] or got['not_called_stale'] or got['a_reviewer_dispatched'])
        deferred = result(explanation='Independent verification: DEFERRED (fix round)', reviewers=lines)
        got = checks('fixround_unverified', deferred, set(), Path('.'))
        self.assertFalse(got['review_blocked_pending_test'] or got['no_reviewer_dispatched'])
        blocked = result(state='blocked', explanation='REVIEW BLOCKED: no VERIFY PASS (fix diff) for this candidate. Next step: /test.', reviewers=lines.replace(': dispatched', ': not dispatched'))
        self.assertTrue(all(checks('fixround_unverified', blocked, set(), Path('.')).values()))

    def test_fix_diff_packet_runs_no_full_suite(self):
        full = result(dispatch='Candidate HEAD abc. Risk · Depth: High · Deep.\nFull suite: run')
        got = checks('testfix_packet', full, set(), Path('.'))
        self.assertFalse(got['packet_scope_is_fix_diff'] or got['no_full_suite'])
        waits = result(state='blocked', explanation='/test runs once, after /review converges.')
        self.assertFalse(checks('testfix_packet', waits, set(), Path('.'))['verifies_now'])
        good = result(dispatch='Candidate HEAD abc. Scope: fix diff.\nFull suite: do not run')
        self.assertTrue(all(checks('testfix_packet', good, set(), Path('.')).values()))

    def test_browser_check_goes_to_the_verifier_without_a_running_app(self):
        owner = result(dispatch='CODE-3: owner — no running app, so the owner checks the page')
        self.assertFalse(checks('route_browser_check', owner, set(), Path('.'))['check_goes_to_the_verifier'])
        good = result(dispatch='- `CODE-3`: verifier — /test serves the candidate on 127.0.0.1 and runs the check')
        self.assertTrue(all(checks('route_browser_check', good, set(), Path('.')).values()))
        with tempfile.TemporaryDirectory() as tmp:
            evidence = prepare(Path(tmp), 'route_browser_check')
            self.assertIn('connection refused', evidence)
            self.assertIn('No verifier has tried this check', evidence)

    def test_test_gate_asks_between_two_candidates(self):
        guessed = result(state='decided', dispatch='To: test-engineer\nCandidate WF-41.', explanation='Using: WF-41, the newest candidate.')
        got = checks('testgate_two_candidates', guessed, set(), Path('.'))
        self.assertFalse(got['asks_which_candidate'] or got['no_packet_sent'])
        labelled = result(state='blocked', explanation='VERIFY BLOCKED: two candidates. Re-run `/test WF-40` or `/test WF-41`.')
        got = checks('testgate_two_candidates', labelled, set(), Path('.'))
        self.assertFalse(got['asks_which_candidate'] or got['not_verify_blocked'])
        asked = result(state='asked', explanation='Two candidates fit. Which one do I verify: WF-40 or WF-41?')
        self.assertTrue(all(checks('testgate_two_candidates', asked, set(), Path('.')).values()))

    def test_figma_packet_reports_a_mismatch_and_fixes_nothing(self):
        plain = result(dispatch='To: figma-test-engineer\nFollow the Verification section of figma-design-to-code. Do not modify production code.\nFull suite: do not run')
        self.assertFalse(checks('testgate_figma', plain, set(), Path('.'))['mismatch_reported_not_fixed'])
        wrong = result(dispatch='To: test-engineer\nReport each mismatch; do not fix it.\nFull suite: do not run')
        self.assertFalse(checks('testgate_figma', wrong, set(), Path('.'))['figma_verifier_dispatched'])
        good = result(dispatch='To: figma-test-engineer\nThe skill says to fix each mismatch. Do not fix a mismatch: report it as VERIFY FAIL with both screenshots.\nFull suite: do not run')
        self.assertTrue(all(checks('testgate_figma', good, set(), Path('.')).values()))
        for line in ('The skill says to fix mismatches. Here you only report them: do not edit production code.',
                     'A mismatch is VERIFY FAIL. Report it and edit no production code, even though the skill says to fix mismatches.'):
            packet = result(dispatch=f'To: figma-test-engineer\n{line}\nFull suite: do not run')
            self.assertTrue(checks('testgate_figma', packet, set(), Path('.'))['mismatch_reported_not_fixed'], line)
        fail_only = result(dispatch='To: figma-test-engineer\nA mismatch is VERIFY FAIL, with both screenshots named. Never judge from memory.\nNo production code edits.\nFull suite: do not run')
        self.assertFalse(checks('testgate_figma', fail_only, set(), Path('.'))['mismatch_reported_not_fixed'])

    def test_packet_carries_handed_on_tasks_and_the_ticket_key(self):
        thin = result(dispatch='To: test-engineer\nCandidate HEAD abc for WF-40.\nFull suite: do not run')
        got = checks('testgate_handed_on', thin, set(), Path('.'))
        self.assertFalse(got['handed_on_task_in_packet'] or got['ticket_key_for_the_refs_trailer'])
        good = result(dispatch='To: test-engineer\nTicket: WF-40 (trailer `Refs: WF-40`).\nHanded on: T002, median time of 1000 click() calls.\nFull suite: do not run')
        self.assertTrue(all(checks('testgate_handed_on', good, set(), Path('.')).values()))

    def test_defect_result_preserves_the_reproduction(self):
        dropped = result(dispatch='Restore the uncommitted test change.\nRoute the fix to /build.', explanation='VERIFY FAIL\nREQ-002 fails.')
        self.assertFalse(checks('testresult_defect', dropped, set(), Path('.'))['reproduction_preserved'])
        good = result(dispatch='Save the failing assertion as a patch outside the worktree.\nRestore verify.py.\nRoute the fix to /build.', explanation='**VERIFY FAIL**\nREQ-002 fails.')
        self.assertTrue(all(checks('testresult_defect', good, set(), Path('.')).values()))
        kept = result(dispatch='Keep the reproduction as the report artifact.\nRoute the fix to /build.', explanation='VERIFY FAIL\nREQ-002 fails.')
        self.assertTrue(checks('testresult_defect', kept, set(), Path('.'))['reproduction_preserved'])

    def test_test_gate_fixtures_hold_what_the_evidence_says(self):
        for name in ('testgate_two_candidates', 'testgate_figma', 'testgate_handed_on', 'testresult_defect'):
            with tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                evidence = prepare(directory, name)
                self.assertIn('no Agent tool', evidence, name)
                self.assertEqual(evidence.count('BUILD COMPLETE\n'), 2 if name == 'testgate_two_candidates' else 1, name)
                self.assertEqual((directory / 'work/WF-41-plan.md').is_file(), name == 'testgate_two_candidates', name)
                self.assertEqual('figma.com' in (directory / 'requirements/WF-40-SPEC.md').read_text(), name == 'testgate_figma', name)
                self.assertEqual('Handed on to /test: T002' in evidence, name == 'testgate_handed_on', name)
                # The defect is real: verify.py passes, and the owner role is refused.
                self.assertEqual(subprocess.run(['python3', 'verify.py'], cwd=tmp).returncode, 0, name)
                refused = subprocess.run(['python3', '-c', 'from ui import click; raise SystemExit(0 if click({"role": "owner"}, lambda: None) else 1)'], cwd=tmp).returncode == 1
                self.assertEqual(refused, name == 'testresult_defect', name)

    def test_full_run_after_review_converges(self):
        fix_diff = result(dispatch='Candidate HEAD abc. Scope: fix diff.\nFull suite: do not run')
        got = checks('testfull_packet', fix_diff, set(), Path('.'))
        self.assertFalse(got['not_a_fix_diff_run'] or got['full_suite_runs'])
        good = result(dispatch='Candidate HEAD abc. Risk · Depth: High · Deep.\nFull suite: run')
        self.assertTrue(all(checks('testfull_packet', good, set(), Path('.')).values()))

    def test_ship_accepts_a_full_run_that_added_no_commits(self):
        waits = result(state='blocked', explanation='SHIP BLOCKED\nThe closing review round comes next.')
        self.assertFalse(checks('shipgate_full_run', waits, set(), Path('.'))['verification_satisfied'])
        good = result(state='decided', explanation='Verification: satisfied\nThe full VERIFY PASS covers this candidate and added no commits.')
        self.assertTrue(all(checks('shipgate_full_run', good, set(), Path('.')).values()))
        self.assertFalse(checks('shipgate_no_full_run', good, set(), Path('.'))['ship_blocked_pending_test'])
        blocked = result(state='blocked', explanation='SHIP BLOCKED\nPASS (fix diff) needs the full-depth run. Next: `/test`.')
        self.assertTrue(all(checks('shipgate_no_full_run', blocked, set(), Path('.')).values()))

    def test_converged_fix_round_names_test_next(self):
        ship = result(explanation='Independent verification: PASS (fix diff)\nNext stage: `/ship`')
        self.assertFalse(checks('reviewend_fix_round', ship, set(), Path('.'))['next_stage_is_test'])
        good = result(explanation='Independent verification: PASS (fix diff)\nNext stage: `/test` once at Deep, then `/ship`')
        self.assertTrue(all(checks('reviewend_fix_round', good, set(), Path('.')).values()))
        with tempfile.TemporaryDirectory() as tmp:
            evidence = prepare(Path(tmp), 'reviewend_fix_round')
            self.assertIn('VERIFY PASS (fix diff)', evidence)
            self.assertNotIn('Next step', evidence)
            self.assertNotIn('/ship', evidence)

    def test_ship_verdicts(self):
        go = result(state='decided', explanation='Ship Decision: GO\nSEC-1: follow-up.')
        no_go = result(state='blocked', explanation='Ship Decision: NO-GO\nNext: `/build`, then `/test` and `/review`.')
        blocked = result(state='blocked', explanation='Ship Decision: SHIP BLOCKED\nAsk the owner.')
        self.assertFalse(checks('ship_preexisting_blocker', go, set(), Path('.'))['not_go'])
        self.assertTrue(all(checks('ship_preexisting_blocker', no_go, set(), Path('.')).values()))
        got = checks('ship_preexisting_blocker', blocked, set(), Path('.'))
        self.assertTrue(got['not_go'] and not got['no_go'])
        self.assertTrue(all(checks('ship_answered_required', go, set(), Path('.')).values()))
        self.assertFalse(checks('ship_answered_required', no_go, set(), Path('.'))['go'])
        self.assertTrue(all(checks('ship_base_check_failed', no_go, set(), Path('.')).values()))
        short = result(state='blocked', explanation='Ship Decision: NO-GO\nNext: `/build` and `/review`.')
        self.assertFalse(checks('ship_base_check_failed', short, set(), Path('.'))['fix_goes_through_test'])

    def test_three_gate_cases_that_must_stop(self):
        go = result(state='decided', explanation='Ship Decision: GO\nCODE-4: the spec answers it.')
        self.assertFalse(checks('ship_open_required', go, set(), Path('.'))['not_go'])
        no_go = result(state='blocked', explanation='Ship Decision: NO-GO\nCODE-4 is an open REQUIRED finding.')
        self.assertTrue(all(checks('ship_open_required', no_go, set(), Path('.')).values()))
        started = result(state='decided', dispatch='CODE-1: dispatch — open', explanation='The notes file is review material.')
        self.assertFalse(checks('fix_other_review_file', started, set(), Path('.'))['run_does_not_start'])
        stopped = result(state='blocked', explanation='The candidate changed after the review. Run `/review` again first.')
        self.assertTrue(all(checks('fix_other_review_file', stopped, set(), Path('.')).values()))
        passed = result(state='decided', explanation='Verification: satisfied')
        self.assertFalse(checks('shipgate_full_run_added_tests', passed, set(), Path('.'))['ship_blocked_pending_closing_round'])
        closing = result(state='blocked', explanation='SHIP BLOCKED\nThe full run added a test commit. Next: the closing `/review` round.')
        self.assertTrue(all(checks('shipgate_full_run_added_tests', closing, set(), Path('.')).values()))
        with tempfile.TemporaryDirectory() as tmp:
            evidence = prepare(Path(tmp), 'fix_other_review_file')
            changed = subprocess.check_output(['git', '-C', tmp, 'diff', '--name-only', 'HEAD~1', 'HEAD'], text=True).split()
            self.assertEqual(changed, ['docs/reviews/WF-40-notes.md'])
            self.assertIn('CODE-1 REQUIRED', evidence)
            self.assertNotIn('CODE-2', evidence)
            self.assertNotIn('user is not None', (Path(tmp) / 'auth.py').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            evidence = prepare(Path(tmp), 'shipgate_full_run_added_tests')
            head = subprocess.check_output(['git', '-C', tmp, 'rev-parse', 'HEAD'], text=True).strip()
            self.assertEqual(subprocess.check_output(['git', '-C', tmp, 'log', '-1', '--format=%s'], text=True).strip(), 'test: the owner role exports')
            self.assertIn(f'Final tree: clean at {head}', evidence)
            self.assertIn('test: the owner role exports" (verify.py only)', evidence)
            self.assertNotIn('Test-only commits: none', evidence.split('VERIFY PASS\n')[1])
            self.assertEqual(subprocess.run(['python3', 'verify.py'], cwd=tmp).returncode, 0)
        with tempfile.TemporaryDirectory() as tmp:
            evidence = prepare(Path(tmp), 'ship_open_required')
            self.assertIn('did not close it as answered', evidence)
            self.assertNotIn('WF-77', evidence)

    def test_ship_stats_run_after_the_resolutions(self):
        early = result(dispatch='check-ledger.py WF-40 --ship\nticket-stats.py WF-40\nreview-sarif.py resolve WF-40 CODE-5=follow-up')
        self.assertFalse(checks('ship_stats_order', early, set(), Path('.'))['stats_after_resolutions'])
        late = result(dispatch='check-ledger.py WF-40 --ship\nreview-sarif.py resolve WF-40 CODE-5=follow-up CODE-6=declined\nticket-stats.py WF-40')
        self.assertTrue(all(checks('ship_stats_order', late, set(), Path('.')).values()))

    def test_ship_fixtures_state_what_each_case_needs(self):
        for name in ('ship_preexisting_blocker', 'ship_answered_required', 'ship_base_check_failed', 'ship_stats_order'):
            with tempfile.TemporaryDirectory() as tmp:
                evidence = prepare(Path(tmp), name)
                self.assertIn('Independent verification: PASS (a VERIFY PASS at Deep', evidence, name)
                self.assertEqual('SEC-1 BLOCKER' in evidence, name == 'ship_preexisting_blocker', name)
                self.assertEqual('WF-77' in evidence, name in ('ship_answered_required', 'ship_stats_order'), name)
                self.assertEqual('exit 1' in evidence, name == 'ship_base_check_failed', name)
                # The pre-existing finding points at code that is in the tree and at the base.
                self.assertIn('session.token', (Path(tmp) / 'export.py').read_text(), name)
                changed = subprocess.check_output(['git', '-C', tmp, 'diff', '--name-only', 'HEAD~1', 'HEAD'], text=True)
                self.assertNotIn('export.py', changed, name)
                self.assertEqual(subprocess.check_output(['git', '-C', tmp, 'status', '--short'], text=True), '', name)

    def test_ship_fixtures_differ_only_in_the_full_run(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            full, none = prepare(Path(one), 'shipgate_full_run'), prepare(Path(two), 'shipgate_no_full_run')
            for evidence in (full, none):
                self.assertIn('Independent verification: PASS (fix diff)', evidence)
                self.assertIn('VERIFY PASS (fix diff)', evidence)
            self.assertEqual(full.count('VERIFY PASS\n'), 1)
            self.assertIn('Test-only commits: none', full)
            self.assertEqual(none.count('VERIFY PASS\n'), 0)
            self.assertIn('No `/test` ran after that review round.', none)
            # The full run names the HEAD the tree holds.
            head = subprocess.check_output(['git', '-C', one, 'rev-parse', 'HEAD'], text=True).strip()
            self.assertIn(f'identical to the recorded candidate {head}', full)

    def test_fix_round_fixtures_state_only_what_each_case_needs(self):
        for name in ('fix_next_stage', 'fixround_verified', 'fixround_unverified', 'testfix_packet', 'testfull_packet'):
            with tempfile.TemporaryDirectory() as tmp:
                evidence = prepare(Path(tmp), name)
                self.assertIn('no Agent tool', evidence, name)
                self.assertNotIn('CODE-2', evidence, name)
                verified = name in ('fixround_verified', 'testfull_packet')
                self.assertEqual('VERIFY PASS (fix diff)' in evidence, verified, name)
                self.assertEqual('BUILD COMPLETE (review fixes)' in evidence, name != 'fix_next_stage', name)
                self.assertEqual('Nothing to fix' in evidence, name == 'testfull_packet', name)
                # A verified fix round carries one declared test-only commit, and the tree holds it.
                files = subprocess.check_output(['git', '-C', tmp, 'show', '--name-only', '--format=%s', 'HEAD'], text=True).split('\n')
                self.assertEqual(files[0] == 'test: refuse a user with no role', verified, name)
                if verified:
                    self.assertEqual([f for f in files[1:] if f], ['verify.py'], name)
                    self.assertEqual(subprocess.run(['python3', 'verify.py'], cwd=tmp).returncode, 0, name)

    def test_probe_fixtures_build_and_state_the_git_facts(self):
        for name in [c for c in cases() if c.startswith(('gate_', 'fix_', 'executor_')) and c != 'fix_next_stage']:
            with tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                evidence = prepare(directory, name)
                self.assertIn('no Agent tool', evidence, name)
                self.assertTrue((directory / 'AGENTS.md').is_file(), name)
                self.assertEqual('BUILD BLOCKED' in evidence, name == 'fix_rerun', name)
                if name == 'executor_fix_trailer':
                    # The tree must hold the fix the packet claims, staged.
                    self.assertIn('user is not None', (directory / 'auth.py').read_text())
                    staged = subprocess.check_output(['git', '-C', tmp, 'diff', '--cached', '--name-only'], text=True).split()
                    self.assertEqual(staged, ['auth.py', 'verify.py'])
                if name == 'gate_spec_pin':
                    self.assertIn('+The export action label must read Save.', evidence)
                    self.assertIn('Status: Approved', (directory / 'requirements/WF-30-SPEC.md').read_text())

    def test_fixtures_build_for_every_decision_case(self):
        for name in [c for c in cases() if c.startswith(('build_', 'review_'))]:
            with tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                evidence = prepare(directory, name)
                self.assertTrue((directory / 'AGENTS.md').is_file(), name)
                self.assertIn('no Agent tool', evidence, name)
                if name.startswith('review_'):
                    self.assertIn('BUILD COMPLETE', evidence, name)
                    self.assertEqual('VERIFY PASS' in evidence, name in ('review_auth_diff', 'review_plain_diff'), name)
                    self.assertEqual('REQ-002' in (directory / 'requirements/WF-40-SPEC.md').read_text(), name != 'review_plain_diff', name)
                else:
                    self.assertTrue((directory / 'work/WF-30-todo.md').is_file(), name)
                    self.assertEqual((directory / 'tests/run.sh').is_file(), name in ('build_shared_db', 'build_pressure_fan_out'), name)


if __name__ == '__main__':
    unittest.main()
