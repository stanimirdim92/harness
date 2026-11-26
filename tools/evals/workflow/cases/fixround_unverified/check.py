import re

from run import parse_decisions


def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    reviewers = parse_decisions(result.get('reviewers', ''), ('code-reviewer', 'blind-reviewer', 'security-auditor', 'distributed-systems-reviewer'), ('not dispatched', 'dispatched'))
    return {
        'reviewed_without_test': result['state'] == 'decided' and not re.search(r'REVIEW BLOCKED', text),
        'not_run_recorded': bool(re.search(r'(?i)Independent verification:\W*NOT RUN \(fix round\)', text)),
        'code_reviewer_dispatched': reviewers.get('code-reviewer') == 'dispatched',
    }
