import re


def checks(result, reads, directory):
    return {'draft_only': result['state'] == 'ready_for_review' and bool(re.search(r'^Status:\s*Draft\s*$', result['spec'], re.M))}
