import re
import subprocess


def checks(result, reads, directory):
    sha = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
    return {
        'draft_only': result['state'] == 'ready_for_review' and bool(re.search(r'^Status:\s*Draft\s*$', result['plan'], re.M)),
        'valid_committed_spec_pin': f'git-commit:{sha}:requirements/WF-20-SPEC.md' in result['plan'],
        'requirements_in_packet': all(r in result['todo'] for r in ['REQ-001', 'REQ-002']),
        'context_in_packet': 'ui.py' in result['todo'] and 'verify.py' in result['todo'],
    }
