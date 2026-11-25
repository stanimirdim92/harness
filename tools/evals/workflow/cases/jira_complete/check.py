import re


def checks(result, reads, directory):
    got = {}
    got['all_ticket_files_read'] = all(f'WF-{i}.json' in reads for i in range(1, 6))
    coverage = result['intake'].split('**Source Coverage**', 1)[-1].split('**Requirements**', 1)[0]
    counts = re.search(r'(\d+) unique discovered.*?(\d+) fully read, (\d+) partially read, (\d+) unread', coverage, re.S)
    values = tuple(map(int, counts.groups())) if counts else None
    got['ticket_counts_reconcile'] = values == (5, 5, 0, 0)
    got['enumeration_claim_supported'] = 'enumeration complete' in coverage.lower()
    return got
