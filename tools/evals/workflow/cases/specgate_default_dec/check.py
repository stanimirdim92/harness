import re


def checks(result, reads, directory):
    steps = result.get('dispatch', '')
    q1 = next((line for line in steps.splitlines() if re.match(r'\W*Q1\b', line)), '')
    return {'decided_by_default': bool(re.match(r'\W*Q1\W+default\b', q1, re.I))}
