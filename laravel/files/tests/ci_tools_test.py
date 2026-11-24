"""Offline infrastructure checks. Every Git mutation uses a temporary repository."""
import os
import json
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreCommitLauncherTest(unittest.TestCase):
    def test_missing_runner_fails_with_setup_instruction(self):
        with tempfile.TemporaryDirectory() as cache:
            result = subprocess.run(
                ["python3", str(ROOT / "bin/pre-commit.py"), "--version"],
                env={**os.environ, "XDG_CACHE_HOME": cache},
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--setup", result.stderr)

    def test_modified_cached_runner_is_never_executed(self):
        with tempfile.TemporaryDirectory() as cache:
            runner = Path(cache) / "leadbuster/pre-commit-4.7.0.pyz"
            runner.parent.mkdir(parents=True)
            runner.write_text("raise RuntimeError('executed untrusted runner')")
            result = subprocess.run(
                ["python3", str(ROOT / "bin/pre-commit.py"), "--version"],
                env={**os.environ, "XDG_CACHE_HOME": cache},
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum", result.stderr)
            self.assertNotIn("executed untrusted runner", result.stderr)


class GitFixtureTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="leadbuster-ci-")
        self.repo = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.git("init", "-q")
        self.git("config", "user.name", "CI fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.hooksPath", "/dev/null")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo).decode().strip()

    def write(self, name, size):
        file = self.repo / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"x" * size)
        self.git("add", "--", name)

    def commit(self):
        self.git("commit", "-qm", "Fixture", "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def size_check(self, *args):
        return subprocess.run(
            ["python3", str(ROOT / "bin/check-file-size.py"), *args],
            cwd=self.repo, capture_output=True, text=True,
            env={k: v for k, v in os.environ.items() if not k.startswith("PRE_COMMIT_")},
        )


class FileSizeTest(GitFixtureTest):
    def test_unborn_index_and_exact_byte_boundary(self):
        self.write("new file.py", 30000)
        self.assertEqual(self.size_check().returncode, 0)
        self.write("new file.py", 30001)
        self.assertNotEqual(self.size_check().returncode, 0)

    def test_uses_staged_blob_not_working_tree(self):
        self.write("partial.py", 30001)
        (self.repo / "partial.py").write_bytes(b"small")
        self.assertNotEqual(self.size_check().returncode, 0)
        self.git("add", "partial.py")
        (self.repo / "partial.py").write_bytes(b"x" * 35000)
        self.assertEqual(self.size_check().returncode, 0)

    def test_oversized_files_can_shrink_but_cannot_grow(self):
        self.write("old.php", 35000)
        self.commit()
        self.write("old.php", 34999)
        self.assertEqual(self.size_check().returncode, 0)
        self.write("old.php", 35001)
        self.assertNotEqual(self.size_check().returncode, 0)

    def test_rename_preserves_allowance_but_copy_is_new(self):
        self.write("old.py", 35000)
        self.commit()
        self.git("mv", "old.py", "renamed\nwith space.py")
        self.assertEqual(self.size_check().returncode, 0)
        self.commit()
        self.write("copy.py", 35000)
        self.assertNotEqual(self.size_check().returncode, 0)

    def test_exclusions_and_deletions(self):
        for name in ["docs/large.md", "composer.lock", "image.svg", "database/schema/test.sql", ".claude/large.md", ".claude/skills/example/large.py"]:
            self.write(name, 35000)
        self.assertEqual(self.size_check().returncode, 0)
        self.write("old.php", 35000)
        self.commit()
        self.git("rm", "old.php")
        self.assertEqual(self.size_check().returncode, 0)

    def test_revision_comparison_ignores_index_and_fails_on_invalid_refs(self):
        base = self.commit()
        self.write("large\nname.py", 35000)
        head = self.commit()
        self.git("rm", "large\nname.py")
        self.assertNotEqual(self.size_check("--from-ref", base, "--to-ref", head).returncode, 0)
        self.assertEqual(self.size_check("--from-ref", head, "--to-ref", head).returncode, 0)
        self.assertNotEqual(self.size_check("--from-ref", "missing", "--to-ref", head).returncode, 0)
        self.assertNotEqual(self.size_check("--from-ref", base).returncode, 0)


class ComparisonRefsTest(GitFixtureTest):
    def resolve(self, event, payload, head=None):
        event_file = self.repo / "event.json"
        event_file.write_text(json.dumps(payload))
        return subprocess.run(
            ["python3", str(ROOT / "bin/ci-refs.py")], cwd=self.repo,
            env={**os.environ, "GITHUB_EVENT_NAME": event,
                 "GITHUB_EVENT_PATH": str(event_file),
                 "GITHUB_SHA": head or self.git("rev-parse", "HEAD")},
            capture_output=True, text=True,
        )

    def test_push_manual_and_missing_or_zero_base(self):
        base = self.commit()
        self.write("new.py", 1)
        head = self.commit()
        for event, payload in [
            ("push", {"before": base}),
            ("workflow_dispatch", {"inputs": {"base_ref": base}}),
        ]:
            result = self.resolve(event, payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"from_ref={base}\n", result.stdout)
            self.assertIn(f"to_ref={head}\n", result.stdout)
        for base in ["", "0" * 40, "missing"]:
            self.assertNotEqual(self.resolve("push", {"before": base}).returncode, 0)
        self.assertNotEqual(self.resolve("push", {"before": head}, head="0" * 40).returncode, 0)

    def test_pr_checks_merge_candidate_and_scans_original_head(self):
        base = self.commit()
        self.git("checkout", "-qb", "feature")
        self.write("feature.py", 1)
        feature = self.commit()
        self.git("checkout", "-q", "--detach", base)
        self.write("main.py", 1)
        main = self.commit()
        self.git("merge", "--no-ff", "-qm", "Merge fixture", feature)
        merged = self.git("rev-parse", "HEAD")
        result = self.resolve("pull_request", {"pull_request": {
            "base": {"sha": main}, "head": {"sha": feature},
        }})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"from_ref={main}\n", result.stdout)
        self.assertIn(f"to_ref={merged}\n", result.stdout)
        self.assertIn(f"scan_to_ref={feature}\n", result.stdout)

    def test_quality_uses_direct_diff_even_for_diverged_pushes(self):
        ancestor = self.commit()
        self.write("before.py", 1)
        base = self.commit()
        self.git("checkout", "-q", "--detach", ancestor)
        self.write("--odd.py", 1)
        self.write("after\nname.py", 2)
        self.write(".yarn/install-state.gz", 2)
        head = self.commit()
        (self.repo / "bin").mkdir()
        (self.repo / "bin/pre-commit.py").write_text(
            "import json,sys\nprint(json.dumps(sys.argv[1:]))\n"
        )
        result = subprocess.run(
            ["python3", str(ROOT / "bin/ci-quality.py")], cwd=self.repo,
            env={**os.environ, "PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": head},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = json.loads(result.stdout)
        self.assertEqual(arguments, [
            "run", "--hook-stage", "manual", "--files",
            "./--odd.py", "./.yarn/install-state.gz", "./after\nname.py",
        ])
        (self.repo / ".yarn/install-state.gz").write_bytes(b"generated on this runner")
        rerun = subprocess.run(
            ["python3", str(ROOT / "bin/ci-quality.py")], cwd=self.repo,
            env={**os.environ, "PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": head},
            capture_output=True, text=True,
        )
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        (self.repo / "after\nname.py").write_text("dirty source")
        rerun = subprocess.run(
            ["python3", str(ROOT / "bin/ci-quality.py")], cwd=self.repo,
            env={**os.environ, "PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": head},
            capture_output=True, text=True,
        )
        self.assertNotEqual(rerun.returncode, 0)


class AggregateGateTest(unittest.TestCase):
    def test_only_successful_dependencies_pass(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        script = textwrap.dedent(workflow.split("python3 - <<'PYTHON'\n")[1].split("          PYTHON")[0])
        with tempfile.TemporaryDirectory() as directory:
            for state in ["success", "failure", "cancelled", "skipped"]:
                with self.subTest(state=state):
                    result = subprocess.run(
                        ["python3", "-c", script],
                        env={**os.environ, "JOB_RESULTS": json.dumps({"quality": {"result": state}}),
                             "GITHUB_STEP_SUMMARY": str(Path(directory) / "summary.md")},
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode == 0, state == "success")


if __name__ == "__main__":
    unittest.main()
