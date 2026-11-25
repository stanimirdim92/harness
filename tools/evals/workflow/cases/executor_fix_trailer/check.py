import re


def checks(result, reads, directory):
    trailers = result['explanation'].strip().split('\n\n')[-1]
    return {
        'refs_trailer': bool(re.search(r'^Refs:\s*WF-40\s*$', trailers, re.M)),
        'task_trailer_names_finding': bool(re.search(r'^Task:.*\bCODE-1\b', trailers, re.M)),
    }
