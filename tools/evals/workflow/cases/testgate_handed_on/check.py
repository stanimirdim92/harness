import re


def checks(result, reads, directory):
    packet = result.get('dispatch', '')
    return {'handed_on_task_in_packet': 'T002' in packet and bool(re.search(r'1000|median', packet))}
