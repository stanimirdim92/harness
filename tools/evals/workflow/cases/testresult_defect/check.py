import re


def checks(result, reads, directory):
    first = next((line for line in result['explanation'].splitlines() if line.strip()), '')
    return {'verify_fail': bool(re.match(r'[\s*#`>]*VERIFY FAIL\b', first))}
