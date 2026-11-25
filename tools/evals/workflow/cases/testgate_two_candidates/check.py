def checks(result, reads, directory):
    text = '\n'.join(result[k] for k in ['explanation', 'intake', 'spec', 'plan', 'todo'])
    return {'asks_which_candidate': result['state'] == 'asked' and 'WF-40' in text and 'WF-41' in text}
