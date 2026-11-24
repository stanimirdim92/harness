"""bin/ci-report.py against a temporary Git repository with fake Deptrac and clover reports."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin/ci-report.py"


class CiReportTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="leadbuster-ci-report-")
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name).resolve()
        self.git("init", "-q")
        self.git("config", "user.name", "CI fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.hooksPath", "/dev/null")
        source = self.repo / "Modules/Socials/app/Services/Feed.php"
        source.parent.mkdir(parents=True)
        source.write_text("".join(f"line {n}\n" for n in range(1, 11)))
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD")
        # Lines 4 and 5 change; every other line is old.
        source.write_text("".join(f"line {n}{' changed' if n in (4, 5) else ''}\n" for n in range(1, 11)))
        self.git("commit", "-qam", "change")
        self.source = str(source)
        self.summary = self.repo / "summary.md"

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo).decode().strip()

    def run_report(self, *args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "GITHUB_STEP_SUMMARY": str(self.summary)},
        )

    def deptrac_report(self, messages, violations, uncovered=0):
        report = self.repo / "deptrac.json"
        report.write_text(json.dumps({
            "Report": {"Violations": violations, "Uncovered": uncovered, "Allowed": 7},
            "files": {self.source: {"messages": messages}},
        }))
        return str(report)

    def test_deptrac_annotates_only_violations_on_changed_lines(self):
        report = self.deptrac_report([
            {"message": "A must not depend on B (Socials_Application on Core_Adapters)", "line": 4, "type": "error"},
            {"message": "A must not depend on C (Socials_Application on Framework_HttpClient)", "line": 9, "type": "error"},
        ], violations=2)

        result = self.run_report("deptrac", report, "--base", self.base)

        self.assertEqual(result.returncode, 1)
        annotations = [line for line in result.stdout.splitlines() if line.startswith("::")]
        self.assertEqual(annotations, [
            "::error file=Modules/Socials/app/Services/Feed.php,line=4::"
            "A must not depend on B (Socials_Application on Core_Adapters)",
        ])
        summary = self.summary.read_text()
        self.assertIn("| 2 | 0 | 7 |", summary)
        self.assertIn("**On lines changed in this change:** 1", summary)
        self.assertIn("| Feature module uses Core internals | 1 |", summary)
        self.assertIn("| Framework or vendor code in the wrong ring | 1 |", summary)

    def test_deptrac_fails_on_an_uncovered_dependency_alone(self):
        report = self.deptrac_report([
            {"message": "A has uncovered dependency on Missing (Socials_Model)", "line": 2, "type": "warning"},
        ], violations=0, uncovered=1)

        result = self.run_report("deptrac", report)

        self.assertEqual(result.returncode, 1)
        self.assertIn("A has uncovered dependency on Missing", self.summary.read_text())
        self.assertEqual([line for line in result.stdout.splitlines() if line.startswith("::")], [])

    def test_deptrac_passes_a_clean_report(self):
        result = self.run_report("deptrac", self.deptrac_report([], violations=0))

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("On lines changed", self.summary.read_text())

    def test_a_zero_base_of_a_new_branch_annotates_nothing(self):
        report = self.deptrac_report([
            {"message": "A must not depend on B (Socials_Application on Core_Adapters)", "line": 4, "type": "error"},
        ], violations=1)

        result = self.run_report("deptrac", report, "--base", "0" * 40)

        self.assertEqual([line for line in result.stdout.splitlines() if line.startswith("::")], [])

    def test_coverage_warns_only_on_changed_lines_that_no_test_runs(self):
        lines = "".join(
            f'<line num="{n}" type="stmt" count="{count}"/>'
            for n, count in ((3, 0), (4, 0), (5, 2), (8, 0))
        )
        clover = self.repo / "clover.xml"
        clover.write_text(
            '<coverage><project><metrics statements="4" coveredstatements="1" methods="2" coveredmethods="1"/>'
            f'<file name="{self.source}"><metrics statements="4" coveredstatements="1"/>{lines}</file>'
            "</project></coverage>"
        )

        result = self.run_report("coverage", str(clover), "--base", self.base)

        self.assertEqual(result.returncode, 0)
        self.assertEqual([line for line in result.stdout.splitlines() if line.startswith("::")], [
            "::warning file=Modules/Socials/app/Services/Feed.php,line=4::No test runs this changed line.",
        ])
        summary = self.summary.read_text()
        self.assertIn("**Total:** 25.0% of lines, 50.0% of methods", summary)
        self.assertIn("| Modules/Socials | 25.0% | 1/4 |", summary)
        self.assertIn("**Changed lines that no test runs:** 1", summary)


if __name__ == "__main__":
    unittest.main()
