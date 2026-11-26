#!/usr/bin/env python3
"""Fixture tests for skills/code-review-and-quality/scripts/suite-scope.py
(ADR 0154): built-in shared paths, the base branch's "Full suite" list, PHP
classes used outside their module, and the focused-test list."""
import io
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / 'claude' / 'skills' / 'code-review-and-quality'
          / 'scripts' / 'suite-scope.py')
spec = importlib.util.spec_from_file_location('ss', SCRIPT)
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

FEED = '<?php\n\nnamespace Modules\\Socials\\Services;\n\nfinal class Feed\n{\n}\n'
SCORE = '<?php\n\nnamespace Modules\\Socials\\Services;\n\nclass Score\n{\n}\n'


class SuiteScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.repo)
        self.git('init', '-q', '-b', 'main')
        self.write('REVIEW.md', '# REVIEW.md\n\n## Full suite\n\n- `app/Support/**`\n')
        self.write('Modules/Socials/app/Services/Feed.php', FEED)
        self.write('Modules/Socials/app/Services/Score.php', SCORE)
        self.write('Modules/Socials/app/Http/FeedController.php',
                   '<?php\nuse Modules\\Socials\\Services\\Feed;\n')
        self.write('Modules/Advertisers/app/Ranker.php', '<?php\nuse Modules\\Socials\\Services\\Score;\n')
        self.write('tests/Feature/Socials/FeedTest.php', '<?php\nuse Modules\\Socials\\Services\\Feed;\n')
        self.git('add', '-A'); self.git('commit', '-qm', 'base')
        self.git('checkout', '-q', '-b', 'ticket')

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *args], check=True, capture_output=True)

    def write(self, path, text):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def change(self, path, text=None):
        old = (self.repo / path).read_text() if (self.repo / path).exists() else ''
        self.write(path, text if text is not None else old + '// changed\n')
        self.git('add', '-A'); self.git('commit', '-qm', 'change')

    def run_script(self):
        with redirect_stdout(io.StringIO()) as out:
            rc = ss.main(['--base', 'main', '--json'])
        return rc, json.loads(out.getvalue())

    def test_class_used_only_inside_its_module_is_focused(self):
        self.change('Modules/Socials/app/Services/Feed.php')
        rc, out = self.run_script()
        self.assertEqual(rc, 0)
        self.assertEqual(out['focused'], ['tests/Feature/Socials/FeedTest.php'])

    def test_class_used_by_another_module_needs_the_full_suite(self):
        self.change('Modules/Socials/app/Services/Score.php')
        rc, out = self.run_script()
        self.assertEqual(rc, 1)
        self.assertIn('Modules/Advertisers/app/Ranker.php',
                      out['reasons']['Modules/Socials/app/Services/Score.php'])

    def test_migration_lockfile_config_and_test_setup(self):
        for path in ('Modules/Socials/database/migrations/2026_add.php', 'composer.lock',
                     'config/queue.php', 'tests/Pest.php', 'phpunit.xml'):
            with self.subTest(path=path):
                self.git('checkout', '-q', '-B', 'ticket', 'main')
                self.change(path, 'x\n')
                rc, out = self.run_script()
                self.assertEqual(rc, 1)
                self.assertIn(path, out['reasons'])

    def test_grouped_import_from_another_module_needs_the_full_suite(self):
        self.write('Modules/Core/app/Feeds.php', '<?php\nuse Modules\\Socials\\Services\\{Feed, Other};\n')
        self.git('add', '-A'); self.git('commit', '-qm', 'grouped import')
        self.git('checkout', '-q', '-B', 'main'); self.git('checkout', '-q', '-B', 'ticket')
        self.change('Modules/Socials/app/Services/Feed.php')
        rc, out = self.run_script()
        self.assertEqual(rc, 1)
        self.assertIn('Modules/Core/app/Feeds.php', out['reasons']['Modules/Socials/app/Services/Feed.php'])

    def test_factory_and_dataset_need_the_full_suite(self):
        for path in ('Modules/Socials/database/factories/FeedFactory.php', 'tests/Datasets/Ids.php'):
            with self.subTest(path=path):
                self.git('checkout', '-q', '-B', 'ticket', 'main')
                self.change(path, '<?php\n')
                rc, out = self.run_script()
                self.assertEqual(rc, 1)
                self.assertIn(path, out['reasons'])

    def test_base_review_md_full_suite_list(self):
        self.change('app/Support/Clock.php', '<?php\n')
        rc, out = self.run_script()
        self.assertEqual(rc, 1)
        self.assertIn('app/Support/**', out['reasons']['app/Support/Clock.php'])

    def test_changed_test_file_is_focused(self):
        self.change('tests/Feature/Socials/FeedTest.php')
        rc, out = self.run_script()
        self.assertEqual(rc, 0)
        self.assertEqual(out['focused'], ['tests/Feature/Socials/FeedTest.php'])

    def test_deleted_class_still_counts_its_outside_callers(self):
        self.git('rm', '-q', 'Modules/Socials/app/Services/Score.php')
        self.git('commit', '-qm', 'delete')
        rc, _ = self.run_script()
        self.assertEqual(rc, 1)

    def test_bad_base_is_exit_2(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(ss.main(['--base', 'nope']), 2)


if __name__ == '__main__':
    unittest.main(verbosity=1)
