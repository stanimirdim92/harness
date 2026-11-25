import re


def checks(result, reads, directory):
    steps = result.get('dispatch', '').splitlines()
    suite = [line for line in steps if 'verify.py' in line and not re.search(r'\b(cat|sed|rg|grep|head|git)\b', line)]
    return {
        'repository_command_used': bool(suite),
        'full_suite_first_in_background': bool(suite) and 'background' in suite[0].lower(),
    }
