# Added `brightdata-plugin@knowledge-work-plugins`

**Decision.** Enabled `brightdata-plugin@knowledge-work-plugins` in
`settings.json`. It is the Bright Data plugin from the claude.ai catalog.
Its catalog id is `plugin_011e6UhbCkoAGkCN3JgHvJY7`, and its upstream is
`brightdata/skills`. The `knowledge-work-plugins` marketplace is already
registered for `qdrant-skills` (ADR 0013), so no new marketplace entry was
needed.

The plugin bundles skills for:

- scraping a page to markdown, past bot detection and CAPTCHAs;
- Google search with structured results;
- structured extraction from 40+ sites;
- Bright Data's MCP tools, SDK, CLI and proxy.

It is added as a plugin, not as vendored files, for the reason in ADR 0013.
Every other real plugin here is added that way. The catalog handles
licensing and updates.

**Rejected — the Anthropic Directory copy.** The catalog also lists a
"Bright Data" plugin in `anthropic-plugin-directory` with the same skills.
The user linked the `knowledge-work-plugins` one. That marketplace is
already registered here, so that is the one enabled.

**Consequences.** The skills load in every session. Their descriptions add
to the always-on catalog that ADR 0039 narrowed. Reassess it with the other
plugins if it goes unused. Calls to Bright Data need an account and API
key. They are configured outside this repository, and nothing here stores
them.
