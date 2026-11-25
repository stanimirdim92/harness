import re


def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    first = next((line for line in text.splitlines() if line.strip()), '')
    verdict = (re.search(r'Ship Decision:\W*(NO-GO|SHIP BLOCKED|GO)\b', first) or [None, ''])[1]
    return {
        'no_go': verdict == 'NO-GO',
        'fix_goes_through_test': bool(re.search(r'/build\b', text)) and bool(re.search(r'/test\b', text)) and bool(re.search(r'/review\b', text)),
    }
