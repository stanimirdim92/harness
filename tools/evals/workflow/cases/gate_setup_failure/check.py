from run import report_name


def checks(result, reads, directory):
    return {'build_blocked': result['state'] == 'blocked' and report_name(result['explanation']) == 'BUILD BLOCKED'}
