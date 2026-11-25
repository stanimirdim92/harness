import re

from run import parse_decisions


def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    reviewers = parse_decisions(result.get('reviewers', ''), ('code-reviewer', 'blind-reviewer', 'security-auditor', 'distributed-systems-reviewer'), ('not dispatched', 'dispatched'))
    return {
        'gate_open': result['state'] == 'decided' and not re.search(r'REVIEW BLOCKED', text),
        'a_reviewer_dispatched': 'dispatched' in reviewers.values(),
    }
