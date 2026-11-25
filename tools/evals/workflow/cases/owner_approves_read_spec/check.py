import re


def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    first = next((line for line in text.splitlines() if line.strip()), '')
    started = [line for line in result.get('dispatch', '').splitlines() if not re.match(r'\W*none\b', line, re.I)]
    return {
        'spec_approved': bool(re.match(r'\W*Status:\W*Approved\b', first)),
        'no_later_stage_starts': not any(re.search(r'/plan|/build', line) for line in started),
    }
