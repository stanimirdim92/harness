#!/usr/bin/env python3
"""component-response-contracts.md says of itself that nothing checks it against its sources. This does
the cheap half: every file in hooks/, agents/ and commands/ is named in the section that catalogues it,
so a new hook or persona cannot go uncatalogued and a renamed one cannot stay."""
import re
import unittest
from pathlib import Path

CLAUDE = Path(__file__).resolve().parents[2] / 'claude'
DOC = (CLAUDE / 'references' / 'component-response-contracts.md').read_text()


def section(title):
    m = re.search(rf'^## \d+\. {re.escape(title)}\n(.*?)(?=^## \d+\. |\Z)', DOC, re.M | re.S)
    return m.group(1)


class ContractsDoc(unittest.TestCase):
    def test_every_hook_is_in_the_hook_table(self):
        hooks = section('Claude hooks')
        for path in sorted((CLAUDE / 'hooks').glob('*.sh')):
            self.assertIn(f'| `{path.name}` |', hooks, path.name)

    def test_every_persona_is_in_the_report_table(self):
        personas = section('Claude agent report contracts')
        for path in sorted((CLAUDE / 'agents').glob('*.md')):
            self.assertIn(f'| `{path.stem}` |', personas, path.stem)

    def test_every_command_is_in_the_stage_table(self):
        commands = section('Command stage-gate contracts')
        for path in sorted((CLAUDE / 'commands').glob('*.md')):
            self.assertIn(f'| `/{path.stem}` |', commands, path.stem)

    def test_the_counts_in_the_prose_match(self):
        # Derived from the directories, so a new file fails here until the prose
        # is updated, rather than the test pinning a stale number.
        words = {6: 'Six', 7: 'Seven', 10: 'Ten', 13: 'Thirteen', 14: 'Fourteen', 15: 'Fifteen', 16: 'Sixteen'}
        hooks = len(list((CLAUDE / 'hooks').glob('*.sh')))
        self.assertIn(f'{words[hooks]} files live in `../hooks/`', DOC)
        self.assertIn(f'{words[len(list((CLAUDE / "agents").glob("*.md")))]} personas live in', DOC)
        self.assertIn(f'{words[len(list((CLAUDE / "commands").glob("*.md")))]} commands live in', DOC)

    def test_findings_reference_is_the_one_definition(self):
        findings = (CLAUDE / 'references' / 'findings.md').read_text()
        # The definitions live in findings.md only; the catalogue points there.
        for marker in ('| BLOCKER | Incorrect behavior', 'json.schemastore.org/sarif'):
            self.assertIn(marker, findings)
            self.assertNotIn(marker, DOC)
        for heading in ('## Dispositions', '## Review SARIF'):
            self.assertIn(heading, findings)


if __name__ == '__main__':
    unittest.main()
