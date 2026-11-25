import re

from run import parse_decisions


def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    reviewers = parse_decisions(result.get('reviewers', ''), ('code-reviewer', 'blind-reviewer', 'security-auditor', 'distributed-systems-reviewer'), ('not dispatched', 'dispatched'))
    return {
        'review_blocked_pending_test': bool(re.search(r'REVIEW BLOCKED', text)) and bool(re.search(r'/test', text)),
        'no_reviewer_dispatched': 'dispatched' not in reviewers.values(),
    }
