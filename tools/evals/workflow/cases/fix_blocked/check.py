from run import report_name


def checks(result, reads, directory):
    report = result['explanation']
    return {
        'build_blocked': result['state'] == 'blocked' and report_name(result['explanation']) == 'BUILD BLOCKED',
        'both_findings_reported': all(f in report for f in ('CODE-1', 'CODE-2')),
    }
