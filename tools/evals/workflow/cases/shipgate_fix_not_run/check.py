def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    blocked = result['state'] == 'blocked' or 'SHIP BLOCKED' in text
    return {'accepts_not_run_fix_round': result['state'] == 'decided' and not blocked}
