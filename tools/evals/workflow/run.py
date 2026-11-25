#!/usr/bin/env python3
"""Isolated native-Claude stage tests; assertions are necessary, not sufficient."""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / 'claude'
SCHEMA = {
    'type': 'object',
    'properties': {
        'state': {'type': 'string', 'enum': ['ready_for_review', 'blocked', 'approved_unchanged', 'decided', 'asked']},
        'explanation': {'type': 'string'},
        'intake': {'type': 'string'}, 'spec': {'type': 'string'},
        'plan': {'type': 'string'}, 'todo': {'type': 'string'},
        # Orchestration decisions (no dispatch happens in the runner): /build's
        # per-workstream concurrent|queued lines, /review's per-persona
        # dispatched|not dispatched lines. Empty for other stages.
        'dispatch': {'type': 'string'}, 'reviewers': {'type': 'string'},
    },
    'required': ['state', 'explanation', 'intake', 'spec', 'plan', 'todo', 'dispatch', 'reviewers'],
    'additionalProperties': False,
}
COMMON_FILES = ['references/repository-precedent.md', 'references/spec-quality-gates.md',
                'references/plan-quality-gates.md', 'references/spec-pin.md',
                'references/ticket-ledger.md']
STAGES = {
    'jira': ['skills/jira-ticket/SKILL.md'],
    'spec': ['commands/spec.md', 'skills/spec-driven-development/SKILL.md',
             'references/templates/spec.md', 'references/templates/bugfix-spec.md'],
    'plan': ['commands/plan.md', 'skills/planning-and-task-breakdown/SKILL.md',
             'references/templates/plan.md', 'references/templates/task.md'],
    'build': ['commands/build.md', 'references/target-selection.md',
              'references/templates/plan.md', 'references/templates/task.md'],
    'review': ['commands/review.md', 'references/target-selection.md',
               'references/reviewer-triggers.md', 'references/verification-triggers.md',
               'references/risk-tiers.md'],
    # Probes for /build's readiness gates, its fix modes and the executor's
    # commit message. `gate` reads what `build` reads; the split keeps the
    # fan-out decision boundary off these cases.
    'gate': ['commands/build.md', 'references/target-selection.md',
             'references/templates/plan.md', 'references/templates/task.md'],
    'fix': ['commands/build.md', 'references/target-selection.md'],
    'executor': ['agents/executor.md', 'skills/executor-development-discipline/SKILL.md'],
    'verifier': ['agents/test-engineer.md'],
    # The executor's completing commit for a planned task.
    'executorsteps': ['agents/executor.md', 'skills/executor-development-discipline/SKILL.md'],
    # The verifier with a /test packet that does not restate its method.
    'verifiersteps': ['agents/test-engineer.md'],
    # A fix round at /review's verification gate and at /test (ADR 0147).
    # `fixreview` reads what `review` reads, under a boundary that names no
    # verification status.
    'fixreview': ['commands/review.md', 'references/target-selection.md',
                  'references/reviewer-triggers.md', 'references/verification-triggers.md',
                  'references/risk-tiers.md'],
    'testgate': ['commands/test.md', 'references/target-selection.md',
                 'references/verification-triggers.md', 'references/risk-tiers.md'],
    'reviewroute': ['commands/review.md', 'references/findings.md'],
    # /test after the verifier has reported: same files as `testgate`.
    'testresult': ['commands/test.md', 'references/target-selection.md',
                   'references/verification-triggers.md', 'references/risk-tiers.md'],
    # /spec before the draft: intake blockers, the Figma read, a `decisions:`
    # rerun, and what a default may decide.
    'specgate': ['commands/spec.md', 'skills/spec-driven-development/SKILL.md',
                 'references/templates/spec.md', 'references/spec-quality-gates.md',
                 'references/risk-tiers.md', 'references/repository-precedent.md'],
    # A gate with the owner's message against it (ADR 0148). AGENTS.md is in
    # the prompt, as in every real session.
    'ownertest': ['AGENTS.md', 'commands/test.md', 'references/target-selection.md',
                  'references/verification-triggers.md', 'references/risk-tiers.md'],
    'ownerverdict': ['AGENTS.md', 'commands/release.md', 'references/target-selection.md',
                     'references/findings.md', 'references/risk-tiers.md'],
    'ownerspec': ['AGENTS.md', 'commands/spec.md', 'skills/spec-driven-development/SKILL.md',
                  'references/templates/spec.md', 'references/spec-quality-gates.md'],
    # The end of a converged fix round: which stage /review names next.
    'reviewend': ['commands/review.md', 'references/findings.md'],
    # /release's verdict and the order of its commands. Every check that is not
    # at issue is stated as passed.
    'shipverdict': ['commands/release.md', 'references/target-selection.md',
                    'references/findings.md', 'references/risk-tiers.md'],
    # /plan with the packets in an external tracker: no todo file exists.
    'plansteps': ['commands/plan.md', 'skills/planning-and-task-breakdown/SKILL.md',
                  'references/plan-quality-gates.md'],
    'shipsteps': ['commands/release.md', 'references/target-selection.md',
                  'references/findings.md', 'references/risk-tiers.md'],
    # /release's independent-verification check after a fix round (ADR 0147).
    'shipgate': ['commands/release.md', 'references/target-selection.md',
                 'references/findings.md', 'references/risk-tiers.md'],
}
PROBE_STAGES = ('gate', 'fix', 'executor', 'verifier', 'fixreview', 'testgate', 'reviewroute', 'testresult', 'shipgate', 'reviewend', 'shipverdict', 'shipsteps', 'specgate', 'ownertest', 'ownerverdict', 'ownerspec', 'plansteps', 'verifiersteps', 'executorsteps')
# The verifier probe's mutants: id, original text, mutated text, and whether
# verify.py still passes with the mutant in place. test_runner.py runs each one.
MUTANTS = (('M1', 'total >= 100', 'total > 100', True),
           ('M2', 'if n < 0:', 'if n <= 0:', True),
           ('M3', 'total >= 100 and member', 'total >= 100 or member', False))


def git(directory, *args, capture=False):
    cmd = ['git', '-C', str(directory), '-c', 'user.name=Fixture owner', '-c', 'user.email=fixture@example.invalid', *args]
    if capture:
        return subprocess.check_output(cmd, text=True).strip()
    subprocess.run(cmd, check=True)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


DECISION_BOUNDARY = {
    'build': 'This trial ends at the dispatch decision. In `dispatch`, give exactly one line per workstream in the form `<ws-id>: concurrent — <evidence>` or `<ws-id>: queued — <condition and evidence>`, where the evidence names the repository file that establishes each condition (independence, dependency-readiness, worktree isolation, runtime isolation of every mutable resource the verification touches, rate-limit headroom). State `decided` when the decision is made; `blocked` if a gate stops dispatch. Leave `reviewers` empty.',
    'review': 'This trial ends at the dispatch decision. In `explanation`, record `Independent verification: NOT REQUIRED` or `Independent verification: PASS` (or REVIEW BLOCKED with the reason). In `reviewers`, give exactly one line per persona — code-reviewer, blind-reviewer, security-auditor, distributed-systems-reviewer — in the form `<persona>: dispatched — <trigger reason>` or `<persona>: not dispatched — <reason>`. State `decided` when the decision is made; `blocked` if a gate stops dispatch. Leave `dispatch` empty.',
    'gate': 'This trial ends at the readiness decision. When dispatch may proceed, set state `decided` and give one `<ws-id>: concurrent — <evidence>` or `<ws-id>: queued — <evidence>` line per workstream in `dispatch`. Otherwise set state `blocked`, leave `dispatch` empty, and write the terminal report in `explanation`: the first line is the report name alone, then the blocker, then the stage or route it goes to. End the report with two lines, `Plan status: <value>` and `Spec status: <value>`, giving the Status each file must read when this run ends; write `unchanged` for a file this run leaves as it is.',
    'fix': 'This trial ends at one of two points. When executor reports are supplied, write the terminal report in `explanation`: the first line is the report name alone, then one line per finding, then the next stage or the route of each blocker; set state `decided` for a complete report and `blocked` for a blocked one, and leave `dispatch` empty. When no executor has run yet, decide the scope: set state `decided` and give one line per open finding in `dispatch`, in the form `<finding-id>: dispatch — <reason>` or `<finding-id>: skip — <reason>`. When the run may not start, set state `blocked`, leave `dispatch` empty, and give the reason and the next step in `explanation`.',
    'fixreview': 'This trial ends at the dispatch decision. In `explanation`, record the `Independent verification:` line with the status /review gives this round, or REVIEW BLOCKED with the reason and the next step. In `reviewers`, give exactly one line per persona — code-reviewer, blind-reviewer, security-auditor, distributed-systems-reviewer — in the form `<persona>: dispatched — <reason>` or `<persona>: not dispatched — <reason>`. State `decided` when reviewers may run; `blocked` if a gate stops dispatch. Leave `dispatch` empty.',
    'testgate': 'This trial ends at the verifier dispatch. When /test verifies now, set state `decided` and put the packet you send to the verifier in `dispatch`. Start the packet with one line, `To: <persona>`, and end it with one line, `Full suite: run` or `Full suite: do not run`. When /test does not verify now, leave `dispatch` empty and write in `explanation` exactly what /test says to the user. Set state `asked` when that is a question to the user, and `blocked` when it is a blocked result.',
    'testresult': 'This trial ends at the result of /test. In `dispatch`, list the steps /test takes before it reports, one per line, in order. In `explanation`, write the result report; its first line is the result name alone. Set state `decided`.',
    'specgate': 'This trial ends before the spec is written. In `dispatch`, list the steps this run takes, one per line, in order. In a step that reads Figma, name each tool it calls. For each choice that drafting raises, add one line: `<Q-id>: default — <option>` or `<Q-id>: open question — <reason>`. In `explanation`, write what /spec says to the user. For a choice decided by default, include its complete `DEC-###` block exactly as it goes into the spec. Set state `decided` when this run goes on to a decision brief or a draft, and `blocked` when it reports and stops.',
    'ownerspec': 'This trial ends when the spec is saved and reported. Write in `explanation` what /spec says to the user; the first line is `Status: <the Status the saved spec header reads>` alone. In `dispatch`, list the stages this run starts after /spec, one per line, or write `none`. Set state `decided`.',
    'reviewend': 'This trial ends at the end of the review round. Write in `explanation` the last two lines of the report: `Independent verification: <status>` and `Next stage: <the one stage that runs next>`. Set state `decided`. Leave `dispatch` empty.',
    'shipverdict': 'This trial ends at the verdict. Write the decision in `explanation`: the first line is `Ship Decision: GO`, `Ship Decision: NO-GO` or `Ship Decision: SHIP BLOCKED` alone, then one line per finding with how /release treats it, then the next step and the stages it goes through. Set state `decided` for GO, and `blocked` for the other two. Leave `dispatch` empty.',
    'executorsteps': 'This trial ends at the completing commit. In `dispatch`, list every file that commit holds, one per line, each with a few words on its change. Return the complete commit message in `explanation`.',
    'verifiersteps': 'This trial ends before your first command runs. In `dispatch`, list every command you run to verify this candidate, one per line, in the order you start them, each with its full arguments. Mark a command you start in the background with `(background)`. Set state `decided`.',
    'plansteps': 'This trial covers two steps of /plan: the plan check before the plan is presented, and the commit after the owner approves it. In `dispatch`, list every command /plan runs in those two steps, one per line, in order, each with its full arguments. Set state `decided`.',
    'shipsteps': 'This trial ends before the verdict. In `dispatch`, list every command /release runs on this candidate, one per line, in the order it runs them, each with its arguments. Set state `decided`.',
    'shipgate': 'This trial ends at the independent-verification check of release.md §1. Write in `explanation` what /release says about that check: the first line is `Verification: satisfied` or `SHIP BLOCKED` alone, then the reason, then the next step. Set state `decided` when the check lets /release continue, and `blocked` when it does not. Leave `dispatch` empty.',
    'reviewroute': 'This trial ends at the routing of the finding. In `dispatch`, give one line per finding, in the form `<finding-id>: verifier — <reason and next step>` or `<finding-id>: owner — <reason and next step>`, naming who runs the check the finding asks for. Set state `decided`.',
    'verifier': 'This trial ends at your decision for each mutant. In `dispatch`, give exactly one line per mutant, in the form `<mutant-id>: killed — <evidence>` or `<mutant-id>: survived — <what you do about it>`. When you add a test, write the exact assertion in that line. Put the mutation-probe lines of your verification report in `explanation`.',
    'executor': 'This trial ends at the commit. Return in `explanation` the complete commit message and nothing else, exactly as you would pass it to `git commit -F`.',
}


def stage_files(stage):
    """The harness files, relative to `claude/`, that a case of this stage reads."""
    return STAGES[stage] + (COMMON_FILES if stage not in ('jira', 'build', 'review') + PROBE_STAGES else [])


WATCHED = Path(__file__).resolve().parent / 'watched.txt'


def watched_paths(cases):
    """The sorted `claude/<path>` of every harness file the stage of any case supplies in its prompt."""
    return sorted({f'claude/{p}' for c in cases for p in stage_files(c['stage'])})


def watched_drift(text, generated):
    """`(missing, extra)`: the generated paths the text lacks, and the text paths that are not generated."""
    listed = set(text.split())
    return sorted(set(generated) - listed), sorted(listed - set(generated))


def file_hashes(files):
    return {p: hashlib.sha256((HARNESS / p).read_bytes()).hexdigest() for p in files}


def prompt(stage, request, directory, evidence):
    files = stage_files(stage)
    chunks = [request, f'Fixture directory: {directory}', evidence,
              'Execution boundary: Read/Glob only, confined to the fixture directory. Do not implement, invoke another stage, simulate human approval, or access external services. Return the actual stage artifact text in the structured output instead of writing files; the runner will save it. Empty strings for artifacts not produced. ready_for_review means a draft may be presented for approval, not that approval exists. For intake it means required intake reading is complete. Report blockers truthfully.']
    stage = {'ownertest': 'testgate', 'ownerverdict': 'shipverdict'}.get(stage, stage)
    if stage in DECISION_BOUNDARY:
        chunks.append(DECISION_BOUNDARY[stage])
    for rel in files:
        chunks.append(f'INSTRUCTIONS FROM {rel}\n{(HARNESS/rel).read_text()}')
    return '\n\n'.join(chunks), files


def report_name(report):
    """The terminal report's name, read from its first non-empty line only."""
    first = next((line for line in report.splitlines() if line.strip()), '')
    match = re.match(r'[\s*#`>]*(BUILD (?:COMPLETE|BLOCKED))\b', first)
    return match.group(1) if match else None


def status_line(report, artifact):
    """The value of a `Plan status:` or `Spec status:` line, lowercased, without markup."""
    match = re.search(rf'^[\s\-*]*`?{artifact} status`?\s*:\s*(.+)$', report, re.M | re.I)
    return re.sub(r'[`*.]', '', match.group(1)).strip().lower() if match else None


def parse_decisions(block, names, verdicts):
    """Map each expected name to the verdict on its `<name>: <verdict>` line.

    `verdicts` is tried in order so a longer alternative ('not dispatched') wins
    over its suffix ('dispatched'). Names may be wrapped in backticks or led by
    a list marker."""
    found = {}
    pattern = re.compile(r'^[\s\-*]*`?(' + '|'.join(map(re.escape, names)) + r')`?\s*:\s*(' + '|'.join(map(re.escape, verdicts)) + r')\b', re.M | re.I)
    for match in pattern.finditer(block):
        found.setdefault(match.group(1).lower(), match.group(2).lower())
    return found


def audit_reads(events, directory):
    """Audit actual tool results; this is not an OS access sandbox."""
    calls = {}
    complete = set()
    confined = True
    for event in events:
        blocks = event.get('message', {}).get('content', [])
        for block in blocks if isinstance(blocks, list) else []:
            if block.get('type') == 'tool_use' and block.get('name') in ['Read', 'Glob']:
                data = block.get('input', {})
                value = data.get('file_path') if block['name'] == 'Read' else data.get('path', '.')
                path = Path(value or '.')
                path = (path if path.is_absolute() else directory / path).resolve()
                confined = confined and path.is_relative_to(directory)
                if block['name'] == 'Glob':
                    pattern = data.get('pattern', '')
                    prefix = re.split(r'[\*?\[]', pattern, maxsplit=1)[0]
                    candidate = (path / prefix).resolve()
                    confined = confined and candidate.is_relative_to(directory)
                calls[block['id']] = (block['name'], path)
            elif block.get('type') == 'tool_result' and not block.get('is_error'):
                name, path = calls.get(block.get('tool_use_id'), (None, None))
                if name != 'Read' or not path.is_relative_to(directory) or not path.is_file():
                    continue
                content = block.get('content', '')
                if not isinstance(content, str):
                    content = '\n'.join(x.get('text', '') for x in content if isinstance(x, dict))
                clean = '\n'.join(re.sub(r'^\s*\d+[\t→]', '', line) for line in content.splitlines())
                if path.read_text().strip() in clean:
                    complete.add(path)
    source_names = {p.name for p in complete if p.parent == directory / 'sources'}
    return source_names, confined


def run_claude(body, directory, destination):
    """Run one `claude` turn on `body` in `directory`. The trace and stderr go to `destination`.
    Returns the stream events and the final result event."""
    command=['claude','-p','--safe-mode','--tools','Read,Glob','--allowedTools','Read','Glob','--permission-mode','dontAsk','--no-session-persistence','--output-format','stream-json','--verbose','--json-schema',json.dumps(SCHEMA)]
    with (destination/'trace.jsonl').open('w') as trace, (destination/'stderr.txt').open('w') as err:
        run=subprocess.run(command,input=body,text=True,cwd=directory,stdout=trace,stderr=err,timeout=240)
    events=[json.loads(line) for line in (destination/'trace.jsonl').read_text().splitlines() if line.startswith('{')]
    final=next((e for e in reversed(events) if e.get('type')=='result'),None)
    if final is None: raise RuntimeError('claude printed no result event')
    if run.returncode or final.get('is_error'): raise RuntimeError(str(final.get('result',final.get('subtype'))))
    return events,final


def run_trial(case, folder):
    """Run one trial of a gate case in `folder`, which exists. Build its own fixture in `folder/fixture`.

    Returns the trial record: `checks`, `cost_usd`, `duration_ms`, `answer_state`
    (the `state` of the model's answer), `explanation` and `model_usage`.
    Raises when the trial cannot be scored: a timeout, a CLI error, an empty
    answer or a check that cannot run."""
    import cases
    folder=Path(folder)
    directory=folder/'fixture';directory.mkdir(parents=True)
    evidence=cases.build_fixture(case,directory)
    body,_=prompt(case['stage'],case['request'],directory,evidence)
    write(folder/'prompt.txt',body)
    before=cases.snapshot(directory)
    events,final=run_claude(body,directory,folder)
    result=final.get('structured_output')
    if not isinstance(result,dict) or not result: raise RuntimeError('claude returned an empty structured output')
    read_names,confined=audit_reads(events,directory)
    checks=cases.evaluate(case,result,read_names,directory,before=before,confined=confined)
    for key in ['intake','spec','plan','todo','dispatch','reviewers']:
        if result.get(key):write(folder/(key+'.md'),result[key])
    return {'checks':checks,'cost_usd':final.get('total_cost_usd'),'duration_ms':final.get('duration_ms'),'answer_state':result['state'],'explanation':result['explanation'],'model_usage':final.get('modelUsage')}


class GatesSuite:
    """The gate cases as a suite for the eval core (`core.py` describes the interface)."""
    name='gates'
    kind='case'
    any_loss_is_worse=True
    model=None

    def all_cases(self):
        import cases
        return list(cases.load_cases().values())

    def instruction_hashes(self, cases):
        return file_hashes(sorted({p for c in cases for p in stage_files(c['stage'])}))

    def run_trial(self, case, folder):
        return run_trial(case,folder)

    def write_watched(self):
        paths=watched_paths(self.all_cases())
        WATCHED.write_text('\n'.join(paths)+'\n')
        print(f'Wrote {len(paths)} paths to {WATCHED}')
        return 0

    def state(self, trial):
        checks=trial.get('checks')
        if not checks: return 'errored'
        return 'pass' if all(checks.values()) else 'fail'


def main():
    import cases
    case_map=cases.load_cases()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=list(case_map), action='append')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    output=(args.output or Path(tempfile.mkdtemp(prefix='workflow-verification-'))).resolve()
    output.mkdir(parents=True,exist_ok=True)
    if (output/'results.json').exists():
        raise SystemExit(f'Refusing to replace existing aggregate evidence: {output}/results.json')
    reports=[]
    for name in args.case or case_map:
        destination=output/name
        if destination.exists(): raise SystemExit(f'Refusing to overwrite case evidence: {destination}')
        destination.mkdir(parents=True)
        case=case_map[name]
        print(f'Running {name}',flush=True)
        try:
            trial=run_trial(case,destination)
            checks=trial['checks']
            report={'case':name,'checks':checks,'assertions_passed':all(checks.values()),'state':trial['answer_state'],'explanation':trial['explanation'],'duration_ms':trial['duration_ms'],'model_usage':trial['model_usage'],'instruction_hashes':file_hashes(stage_files(case['stage'])),'semantic_review':'pending'}
        except (subprocess.TimeoutExpired,KeyError,ValueError,RuntimeError) as exc:
            report={'case':name,'assertions_passed':False,'execution_error':str(exc)}
        write(destination/'result.json',json.dumps(report,indent=2)+'\n')
        reports.append(report)
        write(output/'results.json',json.dumps(reports,indent=2)+'\n')
        print(f'{name}: {"ASSERTIONS PASS; SEMANTIC REVIEW PENDING" if report["assertions_passed"] else "ASSERTIONS FAIL"}',flush=True)
    print(f'Evidence: {output}')
    raise SystemExit(0 if all(r['assertions_passed'] for r in reports) else 1)


if __name__=='__main__':main()
