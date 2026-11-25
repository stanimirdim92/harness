import re


def checks(result, reads, directory):
    steps = result.get('dispatch', '')
    # A step may name the tool to say it is not called.
    called = re.sub(r"\b(no|not|never|without|nor)\W+(?:\w+\W+){0,3}get_design_context", '', steps, flags=re.I)
    return {'no_code_generation_tool': 'get_design_context' not in called}
