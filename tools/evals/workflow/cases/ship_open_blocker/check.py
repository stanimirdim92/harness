import re


def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    first = next((line for line in text.splitlines() if line.strip()), '')
    verdict = (re.search(r'Ship Decision:\W*(NO-GO|SHIP BLOCKED|GO)\b', first) or [None, ''])[1]
    return {'no_go': verdict == 'NO-GO'}
