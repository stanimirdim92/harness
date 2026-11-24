#!/usr/bin/env python3
"""Tests for tools/laravel/sync.py on a fake Leadbuster git repository.

The fake repository stands in for Leadbuster, so CI needs no access to it.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'tools' / 'laravel' / 'sync.py'

MANIFEST = """# test manifest
include static phpstan.neon
include runner bin/worktree-*
include skills .ai/skills/**
include skills .claude/skills/*
skip bin/one-off.py   calls a paid service
watch *
watch bin/**
"""


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
                        'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'})


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.src = root / 'leadbuster'
        self.dst = root / 'laravel'
        self.src.mkdir()
        self.dst.mkdir()
        (self.dst / 'MANIFEST').write_text(MANIFEST)
        git(self.src, 'init', '-q', '-b', 'main')
        self.write('phpstan.neon', 'level: 8\n')
        self.write('bin/worktree-test.sh', '#!/bin/sh\necho run\n')
        os.chmod(self.src / 'bin/worktree-test.sh', 0o755)
        self.write('bin/one-off.py', 'print(1)\n')
        self.write('.ai/skills/pest/SKILL.md', '# pest\n')
        (self.src / '.claude/skills').mkdir(parents=True)
        os.symlink('../../.ai/skills/pest', self.src / '.claude/skills/pest')
        self.write('app/Models/User.php', '<?php\n')
        self.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        git(self.src, 'add', '-A')
        git(self.src, 'commit', '-q', '-m', 'change')

    def head(self):
        return subprocess.run(['git', '-C', str(self.src), 'rev-parse', 'HEAD'],
                              check=True, capture_output=True, text=True).stdout.strip()

    def run_sync(self, mode):
        return subprocess.run(['python3', str(SCRIPT), mode, '--source', str(self.src),
                               '--laravel', str(self.dst)], capture_output=True, text=True)

    def test_apply_copies_included_files_exactly(self):
        result = self.run_sync('apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        files = self.dst / 'files'
        self.assertEqual((files / 'phpstan.neon').read_text(), 'level: 8\n')
        self.assertTrue(os.access(files / 'bin/worktree-test.sh', os.X_OK))
        self.assertEqual(os.readlink(files / '.claude/skills/pest'), '../../.ai/skills/pest')
        self.assertFalse((files / 'bin/one-off.py').exists())
        self.assertFalse((files / 'app').exists())
        self.assertIn(self.head(), (self.dst / 'SOURCE.lock').read_text())

    def test_check_passes_right_after_apply(self):
        self.run_sync('apply')
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_fails_and_names_a_changed_file(self):
        self.run_sync('apply')
        self.write('phpstan.neon', 'level: 9\n')
        self.commit()
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 1)
        self.assertIn('changed  phpstan.neon', result.stdout)

    def test_check_fails_on_a_new_and_a_removed_file(self):
        self.run_sync('apply')
        self.write('bin/worktree-doctor.sh', 'echo ok\n')
        git(self.src, 'rm', '-q', 'bin/worktree-test.sh')
        self.commit()
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 1)
        self.assertIn('added    bin/worktree-doctor.sh', result.stdout)
        self.assertIn('removed  bin/worktree-test.sh', result.stdout)
        self.run_sync('apply')
        self.assertFalse((self.dst / 'files/bin/worktree-test.sh').exists())
        self.assertEqual(self.run_sync('check').returncode, 0)

    def test_a_change_outside_the_manifest_is_not_drift(self):
        self.run_sync('apply')
        self.write('app/Models/User.php', '<?php // changed\n')
        self.commit()
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_uncommitted_changes_are_not_copied(self):
        self.run_sync('apply')
        self.write('phpstan.neon', 'level: 9\n')
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('uncommitted', result.stdout)
        self.run_sync('apply')
        self.assertEqual((self.dst / 'files/phpstan.neon').read_text(), 'level: 8\n')

    def test_an_unlisted_file_in_a_watched_area_blocks_check_and_apply(self):
        self.write('rector.php', '<?php\n')
        self.commit()
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 1)
        self.assertIn('unlisted rector.php', result.stdout)
        result = self.run_sync('apply')
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.dst / 'files').exists())
        self.assertFalse((self.dst / 'SOURCE.lock').exists())

    def test_an_include_that_matches_nothing_is_an_error(self):
        (self.dst / 'MANIFEST').write_text(MANIFEST + 'include static deptrac.php\n')
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 2)
        self.assertIn('deptrac.php', result.stderr)

    def test_a_local_edit_of_a_copy_is_drift(self):
        self.run_sync('apply')
        (self.dst / 'files/phpstan.neon').write_text('edited by hand\n')
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 1)
        self.assertIn('changed  phpstan.neon', result.stdout)

    def test_a_ticket_branch_is_not_read(self):
        self.run_sync('apply')
        git(self.src, 'switch', '-q', '-c', 'LD-1')
        self.write('phpstan.neon', 'level: 9\n')
        self.commit()
        result = self.run_sync('check')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_sync('apply')
        self.assertEqual((self.dst / 'files/phpstan.neon').read_text(), 'level: 8\n')
        git(self.src, 'switch', '-q', 'main')
        git(self.src, 'merge', '-q', 'LD-1')
        self.assertEqual(self.run_sync('check').returncode, 1)

    def test_a_missing_checkout_has_its_own_exit_code(self):
        result = subprocess.run(['python3', str(SCRIPT), 'check', '--source',
                                 str(self.src / 'nope'), '--laravel', str(self.dst)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)

    def test_the_session_hook_warns_on_drift_and_manifest_errors_only(self):
        settings = SCRIPT.parents[2] / '.claude' / 'settings.json'
        command = json.loads(settings.read_text())['hooks']['SessionStart'][0]['hooks'][0]['command']
        fake = Path(self.tmp.name) / 'harness'
        (fake / 'tools/laravel').mkdir(parents=True)
        (fake / 'tools/laravel/sync.py').write_text(
            'import sys; sys.exit(int(open(sys.argv[0] + ".code").read()))\n')
        for code, warns in ((0, False), (1, True), (2, True), (3, False)):
            (fake / 'tools/laravel/sync.py.code').write_text(str(code))
            result = subprocess.run(['bash', '-c', command], capture_output=True, text=True,
                                    env={**os.environ, 'CLAUDE_PROJECT_DIR': str(fake)})
            self.assertEqual(result.returncode, 0)
            self.assertEqual(bool(result.stdout.strip()), warns, f'exit {code}')


if __name__ == '__main__':
    unittest.main()
