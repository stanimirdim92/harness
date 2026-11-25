"""The sandbox a headless eval session runs in.

A suite that starts `claude -p` builds its throwaway project with
`export_repo()` (when the project is a repository at a commit),
`install_harness()` and `commit_baseline()`. It starts the session with
`session_args()` and `run_session()`, which keeps the stream-json trace, and
after the session reads that trace with `audit()`.

The harness is copied into the project, never linked, and the session gets no
`--add-dir`. A link or an added directory would let the session read through
to `claude/evals/`, where the hidden checks of the task evals live. The copy
holds no `evals` folder.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[2] / 'claude'
HARNESS_DIRS = ('commands', 'agents', 'skills', 'references', 'docs', 'hooks')
ALLOWED_TOOLS = ('Read', 'Glob', 'Grep', 'Write', 'Edit', 'Task', 'Agent', 'TodoWrite', 'Skill',
                 # /spec runs its shape check before presenting (commands/spec.md).
                 'Bash(python3 *check-spec.py*)')

# A tool call or command that names one of these is a leak.
LEAK = re.compile(r'evals/add-business/(?:hidden|reference)|claude/evals/')


def _copy_tree(dst, src):
    """Copy `src` to `dst`: the whole directory when `dst` is absent, otherwise
    each entry the project does not already have. A project's own
    `.claude/agents` and the harness combine the same way in real use. No
    `evals` folder is copied, at any depth."""
    ignore = shutil.ignore_patterns('evals')
    if not dst.exists():
        shutil.copytree(src, dst, ignore=ignore, ignore_dangling_symlinks=True)
        return
    for child in sorted(src.iterdir()):
        if child.name == 'evals' or (dst / child.name).exists():
            continue
        if child.is_dir():
            shutil.copytree(child, dst / child.name, ignore=ignore, ignore_dangling_symlinks=True)
        else:
            shutil.copy2(child, dst / child.name)


def install_harness(project, harness=HARNESS):
    """Put a copy of the harness into `<project>/.claude/`. Returns `project`."""
    project = Path(project)
    claude = project / '.claude'
    claude.mkdir(parents=True, exist_ok=True)
    for name in HARNESS_DIRS:
        if (harness / name).is_dir():
            _copy_tree(claude / name, harness / name)
    # The harness rules load as project memory. A project keeps its own
    # CLAUDE.md / AGENTS.md; the harness copy goes beside them, not over them.
    has_own = any(path.exists() for path in (project / 'CLAUDE.md', project / 'AGENTS.md', claude / 'CLAUDE.md'))
    shutil.copy2(harness / 'AGENTS.md', claude / ('AGENTS.md' if has_own else 'CLAUDE.md'))
    settings = json.loads((harness / 'settings.json').read_text())
    # settings.local.json, so a project's own .claude/settings.json still applies.
    (claude / 'settings.local.json').write_text(json.dumps({
        'model': settings['model'],
        'effortLevel': settings.get('effortLevel'),
        'env': {k: v for k, v in settings['env'].items() if k.startswith('CLAUDE_CODE_MAX_SUBAGENT')
                or k.startswith('CLAUDE_CODE_EXPERIMENTAL') or k.startswith('CLAUDE_CODE_FORK')},
        'worktree': settings.get('worktree', {}),
        'permissions': {'defaultMode': 'acceptEdits'},
    }, indent=2))
    return project


def export_repo(project, repo, at):
    """Put the files of `repo` at commit `at` into `project`: no `.git`, no history,
    so a run sees neither what shipped later nor the final spec. A throwaway
    index, not `git archive`: that drops `export-ignore` paths, and a project
    that keeps `tests/` out of its release archives would look like it has no
    tests. Gitignored files (`.env`, `vendor/`) are absent."""
    project = Path(project)
    project.mkdir(parents=True)
    index = project.parent / 'export.index'
    env = {**os.environ, 'GIT_INDEX_FILE': str(index)}
    try:
        subprocess.run(['git', '-C', str(repo), 'read-tree', at], env=env, check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repo), 'checkout-index', '-a', f'--prefix={project.resolve()}/'],
                       env=env, check=True, capture_output=True)
    finally:
        index.unlink(missing_ok=True)
    return project


def commit_baseline(project):
    """Start the project's own one-commit history."""
    for command in (['git', 'init', '-q', '-b', 'main', '.'], ['git', 'add', '-A'],
                    ['git', '-c', 'user.email=f@f', '-c', 'user.name=f', 'commit', '-qm', 'Fixture baseline']):
        subprocess.run(command, cwd=project, check=True, capture_output=True)
    return project


def session_args(prompt, budget, resume=None, allowed_tools=ALLOWED_TOOLS):
    """The `claude -p` command line. It has no `--add-dir`: the session sees
    its own project and the copied `.claude/`, and nothing else."""
    return ['claude', '-p', prompt, *(['--resume', resume] if resume else []),
            '--setting-sources', 'project,local', '--permission-mode', 'acceptEdits',
            '--allowedTools', *allowed_tools,
            '--max-budget-usd', str(budget), '--output-format', 'stream-json', '--verbose']


def run_session(args, cwd, trace=None, timeout=1800):
    """Run a `session_args()` command line in `cwd`. Returns its `result` event.
    With `trace`, the whole stream-json output is saved there first, so
    `audit()` can read it after a failed session too."""
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if trace is not None:
        Path(trace).parent.mkdir(parents=True, exist_ok=True)
        Path(trace).write_text(done.stdout)
    if done.returncode != 0:
        raise RuntimeError(f'claude exited {done.returncode}: {done.stderr[-600:]}')
    for line in reversed(done.stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get('type') == 'result':
            return event
    raise RuntimeError(f'claude printed no result event: {done.stdout[-600:]}')


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def audit(trace_path):
    """Read a stream-json trace. Returns `(leaked, calls)`.

    `calls` lists every tool call, a subagent's included, whose input names
    hidden or reference eval files: `{'tool', 'text', 'subagent'}`. A subagent's
    event carries a `parent_tool_use_id`. Only tool calls count; prose that
    mentions a path does not. This audits what the trace shows; it is not an
    access control."""
    calls = []
    for line in Path(trace_path).read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = event.get('message', {}).get('content', []) if isinstance(event, dict) else []
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            hit = next((s for s in _strings(block.get('input', {})) if LEAK.search(s)), None)
            if hit is not None:
                calls.append({'tool': block.get('name'), 'text': hit,
                              'subagent': bool(event.get('parent_tool_use_id'))})
    return bool(calls), calls
