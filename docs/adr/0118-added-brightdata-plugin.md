# Added `brightdata-plugin@knowledge-work-plugins`

**Decision.** Enabled `brightdata-plugin@knowledge-work-plugins` in
`settings.json`. It is the Bright Data plugin from the claude.ai catalog
(catalog id `plugin_011e6UhbCkoAGkCN3JgHvJY7`, upstream
`brightdata/skills`), listed in the `knowledge-work-plugins` marketplace
that `extraKnownMarketplaces` already registers for `qdrant-skills`
(ADR 0013), so no new marketplace entry was needed. It bundles skills for
web scraping (markdown with bot-detection/CAPTCHA bypass), Google search
with structured results, structured extraction from 40+ sites, Bright
Data's MCP tools, and the Bright Data SDK/CLI/proxy best practices.

Added as a plugin, not vendored files, for the same reason as ADR 0013:
every other real plugin here is added that way, and the catalog handles
licensing and updates.

**Rejected — the Anthropic Directory copy.** The catalog also lists a
"Bright Data" plugin in `anthropic-plugin-directory` with the same skills.
The user linked the `knowledge-work-plugins` one, and that marketplace is
already registered here, so that is the one enabled.

**Consequences.** The skills load in every session. Calls to Bright Data
services need a Bright Data account and API key, configured outside this
repository; nothing here stores it.
