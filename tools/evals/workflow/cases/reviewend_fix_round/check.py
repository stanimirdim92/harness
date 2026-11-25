import re


def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    nxt = next((line for line in text.splitlines() if re.match(r'\W*Next stage:', line, re.I)), '')
    return {'next_stage_is_test': bool(re.match(r'\W*Next stage:\W*/test\b', nxt, re.I))}
