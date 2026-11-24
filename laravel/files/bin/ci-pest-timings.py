"""Write the ten slowest JUnit test cases to the GitHub Actions summary."""
from html import escape
import sys
import xml.etree.ElementTree as ET


def main(report):
    cases = ET.parse(report).iter("testcase")
    slowest = sorted(cases, key=lambda case: float(case.attrib["time"]), reverse=True)[:10]
    print("### Slowest Pest tests\n\n<pre>")
    for case in slowest:
        name = f'{case.attrib["classname"]} — {case.attrib["name"]}'
        print(f'{float(case.attrib["time"]):7.3f}s  {escape(name)}')
    print("</pre>")


if __name__ == "__main__":
    main(sys.argv[1])
