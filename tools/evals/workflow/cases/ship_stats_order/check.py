def checks(result, reads, directory):
    # ticket-stats.py counts the resolutions, so it runs after `resolve` wrote them.
    steps = result.get('dispatch', '').splitlines()


    def at(word):
        return next((i for i, line in enumerate(steps) if word in line), None)


    resolve, stats = at('review-sarif.py resolve'), at('ticket-stats.py')
    return {
        'resolutions_written': resolve is not None,
        'stats_run': stats is not None,
        'stats_after_resolutions': None not in (resolve, stats) and stats > resolve,
    }
