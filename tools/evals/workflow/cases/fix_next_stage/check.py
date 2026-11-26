import re

from run import report_name


def checks(result, reads, directory):
    report = result['explanation']
    m = re.search(r'next', report, re.I)
    after = report[m.start():] if m else ''
    test_at, review_at = after.find('/test'), after.find('/review')
    return {
        'build_complete': result['state'] == 'decided' and report_name(report) == 'BUILD COMPLETE',
        'review_is_the_next_stage': review_at != -1 and (test_at == -1 or review_at < test_at),
    }
