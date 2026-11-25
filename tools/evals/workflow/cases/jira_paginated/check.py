import re


def checks(result, reads, directory):
    got = {}
    got['all_ticket_files_read'] = all(f'WF-{i}.json' in reads for i in range(1, 7))
    got['all_source_pages_read'] = {'WF-1.children-2.json', 'WF-4.comments-2.json'} <= reads
    coverage = result['intake'].split('**Source Coverage**', 1)[-1].split('**Requirements**', 1)[0]
    counts = re.search(r'(\d+) unique discovered.*?(\d+) fully read, (\d+) partially read, (\d+) unread', coverage, re.S)
    values = tuple(map(int, counts.groups())) if counts else None
    got['ticket_counts_reconcile'] = values == (6, 6, 0, 0)
    got['enumeration_claim_supported'] = 'enumeration complete' in coverage.lower()
    return got
