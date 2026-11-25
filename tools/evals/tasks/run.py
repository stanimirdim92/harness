#!/usr/bin/env python3
"""The tasks driver: the whole pipeline on the add-business ticket, headless.

    run.py TRIAL_DIR OUT_DIR [--budget USD]

`setup_trial()` builds the project with `claude/evals/add-business/setup.sh`.
`prepare()` copies the harness into it and, only when the README records a
passing sandbox probe, writes the Bash sandbox setting. `run_trial()` then
runs `/spec`, `/plan`, `/build`, `/test` and `/review` with `claude -p`, one
fresh session per stage.

The owner is scripted. When `/spec` or `/plan` leaves a Draft on disk, the
driver sends one more turn in that session: "I read the whole spec. I approve
it." (ADR 0148: that turn carries no gate override, and nothing before a draft
exists carries approval text.) When `/review` reports a BLOCKER or REQUIRED
finding, the driver runs one fix round the way `/review` routes it:
`/build ADD-1 review fixes`, `/test`, `/review`.

The trial stops with a reason and the stage it stopped at:

- `blocked`: a stage reports BLOCKED;
- `question`: a stage returns without its artifact or report, which means it
  asked the owner something other than the approval (a decision brief, a
  `SPEC CONFLICT`);
- `time`: a stage passes its limit, or the trial passes 90 minutes;
- `not_approved`: the approval turn left the header at Draft;
- `error`: a session failed, or the trial budget is spent;
- `complete`: the last review ran.

`run_trial()` takes the session runner and the clock as arguments. The tests
pass a replay of recorded stage outputs and need no `claude`.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import probe_sandbox
import sandbox

TICKET = 'ADD-1'
ADD_BUSINESS = sandbox.HARNESS / 'evals' / 'add-business'
README = Path(__file__).resolve().parents[1] / 'README.md'
SPEC = f'docs/specs/{TICKET}-SPEC.md'
PLAN = f'docs/tasks/{TICKET}-plan.md'

STAGE_PROMPT = {
    'spec': f'/spec {TICKET}', 'plan': f'/plan {TICKET}', 'build': f'/build {TICKET}',
    'test': f'/test {TICKET}', 'review': f'/review {TICKET}', 'fix': f'/build {TICKET} review fixes',
}
APPROVAL = {'spec': 'I read the whole spec. I approve it.', 'plan': 'I read the whole plan. I approve it.'}

WALL_LIMIT = 90 * 60
STAGE_LIMIT = {'spec': 20 * 60, 'plan': 20 * 60, 'build': 45 * 60, 'test': 25 * 60, 'review': 25 * 60}
SESSION_BUDGET = 10.0
TRIAL_BUDGET = 30.0

# The stages run git, the project's tests and PHP, so Bash is allowed whole. With
# the sandbox probe at `fail` nothing stops a read of the eval content; `audit()` only reports it.
TASK_TOOLS = (*(tool for tool in sandbox.ALLOWED_TOOLS if not tool.startswith('Bash')), 'Bash')

BLOCKED = re.compile(r'\bBLOCKED\b')
FINDINGS = re.compile(r'Findings: (\d+) BLOCKER · (\d+) REQUIRED')
REPORT = {
    'build': re.compile(r'\bBUILD COMPLETE\b'),
    'test': re.compile(r'\bVERIFY (?:PASS|FAIL|NOT REQUIRED)\b'),
    'review': re.compile(r'Findings: \d+ BLOCKER|Nothing to fix'),
}
STATUS = re.compile(r'^\**Status:?\**:?[ \t]*(\w+)', re.M)
SPEC_CONFLICT = re.compile(r'^## SPEC CONFLICT\b', re.M)


class Stop(Exception):
    def __init__(self, reason, stage, detail=''):
        super().__init__(reason)
        self.reason, self.stage, self.detail = reason, stage, detail


def setup_trial(dest, setup=ADD_BUSINESS / 'setup.sh'):
    """Build the trial project from the fixture's seed. Returns `dest`."""
    subprocess.run([str(setup), str(dest)], check=True, capture_output=True, text=True)
    return Path(dest)


def prepare(project, readme_text, harness=sandbox.HARNESS):
    """Put the harness copy into the project and keep it out of `git status`.
    Writes the sandbox setting only when the probe record says `pass`.
    Returns whether prevention is on."""
    project = Path(project)
    sandbox.install_harness(project, harness)
    exclude = project / '.git' / 'info' / 'exclude'
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open('a') as handle:
        handle.write('.claude/\n')
    prevention = probe_sandbox.read_result(readme_text) == 'pass'
    if prevention:
        probe_sandbox.write_setting(project, probe_sandbox.deny_paths(harness))
    return prevention


def header_status(path):
    """The `Status:` word of a spec or plan, or None when the file is absent."""
    path = Path(path)
    if not path.is_file():
        return None
    found = STATUS.search(path.read_text())
    return found.group(1) if found else ''


class Trial:
    def __init__(self, project, out, runner, clock, session_budget, trial_budget, prevention):
        self.project, self.out = Path(project), Path(out)
        self.runner, self.clock = runner, clock
        self.session_budget, self.trial_budget = session_budget, trial_budget
        self.start = clock()
        self.record = {'prevention': prevention, 'turns': [], 'leaked': False, 'leaks': [], 'cost_usd': 0.0,
                       'last_stage': None, 'fix_round': False, 'stop_reason': None, 'stop_stage': None,
                       'stop_detail': ''}

    def send(self, stage, prompt, resume=None):
        record = self.record
        record['last_stage'] = stage
        remaining = WALL_LIMIT - (self.clock() - self.start)
        if remaining <= 0:
            raise Stop('time', stage, 'wall')
        left = self.trial_budget - record['cost_usd']
        if left <= 0:
            raise Stop('error', stage, 'the trial budget is spent')
        timeout = min(STAGE_LIMIT[stage], remaining)
        args = sandbox.session_args(prompt, round(min(self.session_budget, left), 4), resume, allowed_tools=TASK_TOOLS)
        trace = self.out / f'{len(record["turns"]) + 1:02d}-{stage}.jsonl'
        try:
            event = self.runner(args, self.project, trace=trace, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise Stop('time', stage, 'stage' if timeout >= STAGE_LIMIT[stage] else 'wall')
        except RuntimeError as err:
            raise Stop('error', stage, str(err)[:300])
        leaked, calls = sandbox.audit(trace) if trace.is_file() else (False, [])
        record['leaked'] = record['leaked'] or leaked
        record['leaks'].extend(calls)
        record['cost_usd'] += event.get('total_cost_usd') or 0
        record['turns'].append({'stage': stage, 'prompt': prompt, 'resume': resume, 'trace': trace.name,
                                'session_id': event.get('session_id'), 'cost_usd': event.get('total_cost_usd'),
                                'num_turns': event.get('num_turns'), 'duration_ms': event.get('duration_ms')})
        if event.get('is_error'):
            raise Stop('error', stage, str(event.get('subtype') or event.get('result'))[:300])
        text = event.get('result') or ''
        found = BLOCKED.search(text)
        if found:
            raise Stop('blocked', stage, text[max(0, found.start() - 20):found.end() + 120].strip())
        return event

    def approve(self, stage, event, rel):
        """The scripted owner turn, in the session that presented the draft."""
        if not event.get('session_id'):
            raise Stop('error', stage, 'the draft session has no id to resume')
        self.send(stage, APPROVAL[stage], resume=event['session_id'])
        if header_status(self.project / rel) != 'Approved':
            raise Stop('not_approved', stage, f'{rel} is still not Approved after the owner turn')

    def draft_stage(self, stage, rel):
        event = self.send(stage, STAGE_PROMPT[stage])
        path = self.project / rel
        status = header_status(path)
        if status is None:
            raise Stop('question', stage, f'no {rel}: the stage asked the owner something')
        if SPEC_CONFLICT.search(path.read_text()):
            raise Stop('question', stage, 'SPEC CONFLICT in the plan')
        if status == 'Draft':
            self.approve(stage, event, rel)

    def command_stage(self, stage, prompt):
        text = self.send(stage, prompt).get('result') or ''
        if not REPORT[stage].search(text):
            raise Stop('question', stage, 'the stage ended without its report: ' + text[:200])
        return text

    def run(self):
        record = self.record
        try:
            self.draft_stage('spec', SPEC)
            self.draft_stage('plan', PLAN)
            self.command_stage('build', STAGE_PROMPT['build'])
            self.command_stage('test', STAGE_PROMPT['test'])
            found = FINDINGS.search(self.command_stage('review', STAGE_PROMPT['review']))
            if found and int(found.group(1)) + int(found.group(2)) > 0:
                record['fix_round'] = True
                self.command_stage('build', STAGE_PROMPT['fix'])
                self.command_stage('test', STAGE_PROMPT['test'])
                self.command_stage('review', STAGE_PROMPT['review'])
            record['stop_reason'] = 'complete'
        except Stop as stop:
            record.update({'stop_reason': stop.reason, 'stop_stage': stop.stage, 'stop_detail': stop.detail})
        record['wall_s'] = round(self.clock() - self.start, 1)
        return record


def run_trial(project, out, runner=sandbox.run_session, clock=time.monotonic, session_budget=SESSION_BUDGET,
              trial_budget=TRIAL_BUDGET, prevention=False):
    """Run the pipeline in `project`. Traces go to `out`. Returns the trial record."""
    Path(out).mkdir(parents=True, exist_ok=True)
    return Trial(project, out, runner, clock, session_budget, trial_budget, prevention).run()


def render_report(record):
    """The first line says whether prevention was on (REQ-031)."""
    lines = ['prevention on: Bash reads under claude/evals/ are denied' if record['prevention']
             else 'prevention off: detection only']
    reason = record['stop_reason']
    lines.append('Trial complete' if reason == 'complete' else
                 f'Stopped: {reason} at /{record["stop_stage"]}: {record.get("stop_detail", "")}')
    lines.append(f'Last stage: /{record["last_stage"]}, fix round: {"yes" if record.get("fix_round") else "no"}')
    lines.append('Leak audit: ' + (f'LEAKED, {len(record["leaks"])} tool call(s) name eval files'
                                   if record['leaked'] else 'clean'))
    lines.append(f'{len(record["turns"])} turn(s), ${record["cost_usd"]:.4f}')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('trial', type=Path, help='the trial project folder; it must not exist')
    parser.add_argument('out', type=Path, help='where the traces, trial.json and report.txt go')
    parser.add_argument('--budget', type=float, default=TRIAL_BUDGET, help='USD for the whole trial')
    args = parser.parse_args(argv)
    setup_trial(args.trial)
    prevention = prepare(args.trial, README.read_text())
    record = run_trial(args.trial, args.out, trial_budget=args.budget, prevention=prevention)
    (args.out / 'trial.json').write_text(json.dumps(record, indent=2) + '\n')
    report = render_report(record)
    (args.out / 'report.txt').write_text(report)
    print(report, end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
