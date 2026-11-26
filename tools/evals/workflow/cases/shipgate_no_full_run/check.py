def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    blocked = result['state'] == 'blocked' or 'SHIP BLOCKED' in text
    return {'accepts_fix_diff_pass': result['state'] == 'decided' and not blocked}
