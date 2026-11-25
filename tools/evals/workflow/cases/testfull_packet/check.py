import re


def checks(result, reads, directory):
    packet = result.get('dispatch', '')
    # The packet's own scope. A quoted earlier report names its fix-diff scope
    # too: skip the "Previous VERIFY report" line and the indented lines under it.
    own, quoted = [], False
    for line in packet.splitlines():
        if re.search(r'previous VERIFY report', line, re.I):
            quoted = True
            continue
        if quoted and line.startswith(('  ', '\t', '>')):
            continue
        quoted = False
        own.append(line)
    return {'not_a_fix_diff_run': not re.search(r'Scope:\W*fix diff', '\n'.join(own), re.I)}
