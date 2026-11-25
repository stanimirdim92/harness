import re


def checks(result, reads, directory):
    steps = result.get('dispatch', '')
    q1 = next((line for line in steps.splitlines() if re.match(r'\W*Q1\b', line)), '')
    # The ticket asks for archived users and the repository leaves them
    # out. The ticket text settles it: no question, and they stay in.
    return {
        'decided_by_default': bool(re.match(r'\W*Q1\W+default\b', q1, re.I)),
        'ticket_behavior_kept': bool(re.search(r'\binclud', q1, re.I)) and not re.search(r'\b(leave|leaves|left) (them |archived users )?out|\bexclud|\bomit', q1, re.I),
    }
