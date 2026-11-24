"""Turn Deptrac and coverage reports into a GitHub Actions summary and line annotations.

    python3 bin/ci-report.py deptrac deptrac.json [--base SHA]
    python3 bin/ci-report.py coverage clover.xml [--base SHA]

The summary (Markdown) goes to $GITHUB_STEP_SUMMARY, or to stdout outside Actions.
Annotations go to stdout. GitHub shows only 10 annotations of a kind per step, so they
cover only the lines changed since --base; the summary covers the whole report.
The deptrac mode exits 1 when the report has a violation or an uncovered dependency.
"""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path.cwd().resolve()
ZERO_SHA = re.compile(r"^0+$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
LAYER_PAIR = re.compile(r"\((\w+) on (\w+)\)$")


def relative(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path


def changed_lines(base):
    """Map each file changed since base to the set of its added or changed line numbers."""
    if not base or ZERO_SHA.match(base):
        return {}
    diff = subprocess.run(
        ["git", "diff", "--unified=0", "--no-color", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout
    changed = defaultdict(set)
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif current and (hunk := HUNK.match(line)):
            start, count = int(hunk[1]), int(hunk[2] or 1)
            changed[current].update(range(start, start + count))
    return dict(changed)


def escape_data(text):
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotate(level, path, line, message):
    print(f"::{level} file={path},line={line}::{escape_data(message)}")


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def write_summary(markdown):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as summary:
            summary.write(markdown + "\n")
    else:
        sys.stdout.write(markdown + "\n")


def module_of(layer):
    return layer.split("_", 1)[0]


def violation_kind(source, target):
    source_module, target_module = module_of(source), module_of(target)
    if target_module in ("Framework", "Vendor", "App", "PhpInternal"):
        return "Framework or vendor code in the wrong ring"
    if source_module == target_module:
        return "Outward dependency inside a module"
    if source_module == "Core":
        return "Core depends on a feature module"
    if target_module == "Core":
        return "Feature module uses Core internals"
    return "Advertisers and Socials depend on each other"


def deptrac(report_path, base):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    totals = report["Report"]
    changed = changed_lines(base)
    pairs, kinds, per_file = Counter(), Counter(), Counter()
    uncovered, new = [], []
    for absolute, entry in report.get("files", {}).items():
        path = relative(absolute)
        for message in entry.get("messages", []):
            text, line = message["message"], int(message.get("line") or 1)
            if message.get("type") == "error":
                pair = LAYER_PAIR.search(text)
                if pair:
                    pairs[(pair[1], pair[2])] += 1
                    kinds[violation_kind(pair[1], pair[2])] += 1
                per_file[path] += 1
            else:
                uncovered.append((path, line, text))
            if line in changed.get(path, ()):
                new.append((path, line, text))

    parts = [
        "### Architecture (Deptrac)",
        table(["Violations", "Uncovered", "Allowed"],
              [[totals.get("Violations", 0), totals.get("Uncovered", 0), totals.get("Allowed", 0)]]),
    ]
    if base and not ZERO_SHA.match(base):
        parts.append(f"**On lines changed in this change:** {len(new)}")
    if kinds:
        parts += ["#### By kind", table(["Kind", "Violations"], kinds.most_common())]
        parts += ["<details><summary>By layer pair</summary>\n",
                  table(["From", "To", "Violations"], [[a, b, n] for (a, b), n in pairs.most_common()]),
                  "\n</details>"]
        parts += ["<details><summary>Files with the most violations</summary>\n",
                  table(["File", "Violations"], [[f"`{f}`", n] for f, n in per_file.most_common(25)]),
                  "\n</details>"]
    if uncovered:
        parts += ["#### Uncovered (in no layer)",
                  table(["File", "Line", "Dependency"], [[f"`{p}`", l, t] for p, l, t in uncovered])]
    write_summary("\n\n".join(parts))

    for path, line, text in new:
        annotate("error", path, line, text)
    return 1 if totals.get("Violations", 0) or totals.get("Uncovered", 0) else 0


def number(element, key):
    """Read an integer attribute of a clover element; a missing element or attribute counts as 0."""
    return int(element.get(key) or 0) if element is not None else 0


def coverage(clover_path, base):
    root = ET.parse(clover_path).getroot()
    changed = changed_lines(base)
    areas = defaultdict(lambda: [0, 0])
    folders = defaultdict(lambda: [0, 0])
    missed = []
    for file in root.iter("file"):
        path = relative(file.get("name") or "")
        parts = path.split("/")
        area = "/".join(parts[:2]) if parts[0] == "Modules" else parts[0]
        folder = "/".join(parts[:4]) if parts[0] == "Modules" else "/".join(parts[:2])
        metrics = file.find("metrics")
        statements, covered = number(metrics, "statements"), number(metrics, "coveredstatements")
        for bucket in (areas[area], folders[folder]):
            bucket[0] += covered
            bucket[1] += statements
        lines = changed.get(path, ())
        missed += [(path, number(line, "num")) for line in file.iter("line")
                   if line.get("type") == "stmt" and line.get("count") == "0" and number(line, "num") in lines]

    def percent(covered, total):
        return f"{100 * covered / total:.1f}%" if total else "–"

    project = root.find("project/metrics")
    rows = [[name, percent(c, t), f"{c}/{t}"] for name, (c, t) in sorted(areas.items())]
    parts = [
        "### Backend coverage (lines)",
        f"**Total:** {percent(number(project, 'coveredstatements'), number(project, 'statements'))} of lines, "
        f"{percent(number(project, 'coveredmethods'), number(project, 'methods'))} of methods",
        table(["Area", "Lines", "Covered"], rows),
        "<details><summary>By folder, lowest first</summary>\n",
        table(["Folder", "Lines", "Covered"],
              [[f"`{name}`", percent(c, t), f"{c}/{t}"]
               for name, (c, t) in sorted(folders.items(), key=lambda item: item[1][0] / max(item[1][1], 1))]),
        "\n</details>",
    ]
    if base and not ZERO_SHA.match(base):
        by_file = defaultdict(list)
        for path, line in missed:
            by_file[path].append(line)
        parts.append(f"**Changed lines that no test runs:** {len(missed)}")
        if by_file:
            parts.append(table(["File", "Lines"], [[f"`{p}`", ", ".join(map(str, sorted(l)))] for p, l in sorted(by_file.items())]))
    write_summary("\n\n".join(parts))

    for path, line in missed:
        annotate("warning", path, line, "No test runs this changed line.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kind", choices=["deptrac", "coverage"])
    parser.add_argument("report")
    parser.add_argument("--base", default="", help="commit to compare with; annotations cover lines changed since it")
    args = parser.parse_args(argv)
    return (deptrac if args.kind == "deptrac" else coverage)(args.report, args.base)


if __name__ == "__main__":
    sys.exit(main())
