import re

from run import parse_decisions


def checks(result, reads, directory):
    block = result.get('dispatch', '')
    verdict = parse_decisions(block, ['M1', 'M2', 'M3'], ('killed', 'survived'))
    line = {m.group(1).upper(): m.group(0) for m in re.finditer(r'^[\s\-*]*`?(M[123])`?\s*:.*$', block, re.M | re.I)}
    return {
        'killed_and_survived_as_run': verdict == {'m1': 'survived', 'm2': 'survived', 'm3': 'killed'},
        # M1 leaves the boundary total untested: the missing case is total 100 for a member.
        'gap_gets_the_boundary_test': bool(re.search(r'discount\(\s*100\s*,\s*True\s*\)\s*==\s*10', line.get('M1', ''))),
        # M2 is equivalent: clamp(0) is 0 either way. No assertion can tell the two apart.
        'equivalent_mutant_gets_a_reason': bool(re.search(r'equivalent|no test can|cannot be killed|nothing\b.{0,40}\bobserv|same (result|value|output|behaviou?r)|identical', line.get('M2', ''), re.I)),
        'no_test_claimed_for_equivalent': not re.search(r'\bassert\b[^|]*==', line.get('M2', '')),
    }
