def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    return {'ship_blocked_pending_closing_round': result['state'] == 'blocked' and 'SHIP BLOCKED' in text and '/review' in text}
