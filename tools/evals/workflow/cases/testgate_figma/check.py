import re


def checks(result, reads, directory):
    packet = result.get('dispatch', '')
    about_mismatch = [line for line in packet.splitlines() if re.search(r'mismatch', line, re.I)]
    # The Figma skill says to fix a mismatch. The packet must say: report it, edit no production code.
    return {'mismatch_reported_not_fixed': any(re.search(r"\b(do not|don't|never|not)\b[^.\n]{0,60}\b(fix|edit|modify)|\bedits? no\b", line, re.I) for line in about_mismatch)}
