"""Integration checks for the prepared hook environments; temporary Git fixtures only."""
import os
from pathlib import Path
import re
import secrets
import shutil
import shlex
import subprocess
import unittest

from ci_tools_test import GitFixtureTest, ROOT


class HookIntegrationTest(GitFixtureTest):
    def prepare_launcher(self, config):
        for name in [".githooks/pre-commit", "bin/pre-commit.py"]:
            destination = self.repo / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        (self.repo / ".pre-commit-config.yaml").write_text(config)
        self.git("add", ".")
        self.commit()
        self.git("config", "core.hooksPath", ".githooks")

    def hook(self):
        return subprocess.run(
            ["bash", ".githooks/pre-commit"], cwd=self.repo,
            capture_output=True, text=True,
        )

    def test_partial_staging_and_linked_worktree(self):
        self.prepare_launcher("""repos:
  - repo: local
    hooks:
      - id: fixture
        name: fixture
        language: unsupported
        entry: python3 -c "import pathlib,sys; sys.exit(pathlib.Path('candidate.txt').read_text() != 'staged')"
        files: ^candidate.txt$
        pass_filenames: false
""")
        linked = self.repo.parent / (self.repo.name + "-linked")
        self.git("worktree", "add", "-q", "--detach", str(linked))
        self.addCleanup(lambda: subprocess.run(
            ["git", "worktree", "remove", "--force", str(linked)], cwd=self.repo, check=True
        ))
        self.repo = linked
        file = linked / "candidate.txt"
        file.write_text("staged")
        self.git("add", "candidate.txt")
        file.write_text("unstaged")
        result = self.hook()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(file.read_text(), "unstaged")
        self.assertEqual(self.git("show", ":candidate.txt"), "staged")
        file.write_text("bad staged")
        self.git("add", "candidate.txt")
        file.write_text("staged")
        self.assertNotEqual(self.hook().returncode, 0)
        self.assertEqual(file.read_text(), "staged")

    def test_option_like_filename_reaches_formatter_as_a_file(self):
        config = (ROOT / ".pre-commit-config.yaml").read_text()
        arguments = shlex.split(re.search(r"entry: (yarn prettier[^\n]+)", config).group(1))[2:]
        # Force a parser for this extensionless filename, keeping the real argument terminator.
        arguments.insert(0, "--parser=typescript")
        entry = shlex.join([str(ROOT / "node_modules/.bin/prettier"), *arguments])
        self.prepare_launcher(f"""repos:
  - repo: local
    hooks:
      - id: formatter
        name: formatter
        language: unsupported
        entry: {entry}
""")
        (self.repo / "--version").write_text("const = ;\n")
        self.git("add", "--", "--version")
        result = self.hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SyntaxError", result.stdout + result.stderr)
        self.assertEqual((self.repo / "--version").read_text(), "const = ;\n")

    def test_staged_secret_and_deleted_intermediate_secret_are_detected_redacted(self):
        config = (ROOT / ".pre-commit-config.yaml").read_text()
        revision = re.search(
            r"https://github.com/gitleaks/gitleaks\s+rev: ([a-f0-9]{40})", config
        ).group(1)
        self.prepare_launcher(f"""repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: {revision}
    hooks:
      - id: gitleaks
""")
        base = self.git("rev-parse", "HEAD")
        token = "ghp_" + secrets.token_hex(20)
        (self.repo / "credential.txt").write_text(f"token = '{token}'\n")
        self.git("add", "credential.txt")
        result = self.hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("leaks found", result.stdout + result.stderr)
        self.assertTrue(token not in result.stdout + result.stderr, "Secret output must be redacted")
        # Build a history fixture. These commits intentionally bypass only the fixture hook.
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "Synthetic secret")
        self.git("rm", "credential.txt")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "Remove synthetic secret")
        head = self.git("rev-parse", "HEAD")
        (self.repo / ".pre-commit-config.yaml").write_text(f"""repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: {revision}
    hooks:
      - id: gitleaks
        entry: gitleaks git --redact --no-banner --log-opts={base}..{head}
        always_run: true
""")
        self.git("add", ".pre-commit-config.yaml")
        result = self.hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("leaks found", result.stdout + result.stderr)
        self.assertTrue(token not in result.stdout + result.stderr, "Secret output must be redacted")


if __name__ == "__main__":
    unittest.main()
