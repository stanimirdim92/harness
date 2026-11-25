def checks(result, reads, directory):
    return {'run_does_not_start': result['state'] == 'blocked' and not result.get('dispatch', '').strip()}
