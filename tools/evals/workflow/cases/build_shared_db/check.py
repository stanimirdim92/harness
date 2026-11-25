from run import parse_decisions


def checks(result, reads, directory):
    dispatch = parse_decisions(result.get('dispatch', ''), ('ws-label', 'ws-report'), ('concurrent', 'queued'))
    concurrent = sum(v == 'concurrent' for v in dispatch.values())
    return {
        'both_workstreams_decided': set(('ws-label', 'ws-report')) <= set(dispatch),
        'shared_runtime_not_fanned_out': concurrent <= 1,
    }
