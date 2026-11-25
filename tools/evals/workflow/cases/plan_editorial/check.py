import re


def checks(result, reads, directory):
    original = (directory / 'work/WF-20-plan.md').read_text()
    return {
        'editorial_state': bool(re.search(r'^Status:\s*Approved\s*$', result['plan'], re.M)) and 'Handoff: Ready for /build' in result['plan'],
        'only_requested_title_changed': result['plan'].strip() == original.replace('Dowload', 'Download').strip(),
        'task_packet_unchanged': not re.search(r'^(?:#{1,3} |Status:|Handoff:|\*\*Requirements:|- \[ \])', result['todo'], re.M)
                                 or result['todo'].strip() == (directory / 'work/WF-20-todo.md').read_text().strip(),
    }
