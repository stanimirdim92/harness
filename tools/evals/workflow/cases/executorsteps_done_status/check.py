import re


def checks(result, reads, directory):
    todo = [line for line in result.get('dispatch', '').splitlines() if 'WF-20-todo.md' in line]
    return {'status_set_to_done': any(re.search(r'\bDone\b', line) for line in todo)}
