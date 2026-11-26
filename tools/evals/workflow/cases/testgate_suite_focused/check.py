import re


def checks(result, reads, directory):
    packet = result.get('dispatch', '')
    return {'mutation_probes_stay': bool(re.search(r'mutation', packet, re.I)) and not re.search(r"\b(skip|no|without|omit)\W+(?:\w+\W+){0,3}mutation", packet, re.I)}
