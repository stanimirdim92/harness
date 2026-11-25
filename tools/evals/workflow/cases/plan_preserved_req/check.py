import re
import subprocess


def checks(result, reads, directory):
    index = [line for line in result['plan'].splitlines() if re.match(r'\s*- \[ \] T\d{3}\b', line)]
    sha = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
    return {
        'draft_only': result['state'] == 'ready_for_review' and bool(re.search(r'^Status:\s*Draft\s*$', result['plan'], re.M)),
        'valid_committed_spec_pin': f'git-commit:{sha}:requirements/WF-20-SPEC.md' in result['plan'],
        'requirements_in_packet': all(r in result['todo'] for r in ['REQ-001', 'REQ-002']),
        'context_in_packet': 'ui.py' in result['todo'] and 'verify.py' in result['todo'],
        # REQ-002 is behavior the change must preserve. It still names a task.
        'preserved_req_has_task': any('REQ-002' in line for line in index),
    }
