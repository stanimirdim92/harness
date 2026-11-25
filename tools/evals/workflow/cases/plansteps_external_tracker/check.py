import re


def checks(result, reads, directory):
    # The packets live in a tracker: no todo file to check or to stage.
    steps = result.get('dispatch', '').splitlines()
    check = [line for line in steps if 'check-plan.py' in line]
    staged = [line for line in steps if re.search(r'\bgit\s+(add|commit)\b', line)]
    return {
        'check_plan_runs': bool(check),
        'check_has_no_todo': bool(check) and not any('todo' in line for line in check),
        'stages_the_plan_alone': (any('WF-20-plan.md' in line for line in staged) and not any('todo' in line for line in staged)
                                  and not any(re.search(r'git\s+add\s+(-A|--all|\.)(\s|$)|commit\s+-\w*a', line) for line in staged)),
    }
