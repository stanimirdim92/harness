import re


def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    first = next((line for line in text.splitlines() if line.strip()), '')
    verdict = (re.search(r'Ship Decision:\W*(NO-GO|SHIP BLOCKED|GO)\b', first) or [None, ''])[1]
    return {
        'not_go': verdict in ('NO-GO', 'SHIP BLOCKED'),
        'ship_blocked': verdict == 'SHIP BLOCKED',
        'owner_may_accept_or_defer': bool(re.search(r'\baccept', text, re.I)) and bool(re.search(r'\bdefer', text, re.I)),
    }
