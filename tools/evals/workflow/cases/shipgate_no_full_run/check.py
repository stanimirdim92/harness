def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    return {'ship_blocked_pending_test': result['state'] == 'blocked' and 'SHIP BLOCKED' in text and '/test' in text}
