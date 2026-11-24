---
paths:
  - 'tests/Feature/**/*.php'
---

# Feature

## Mockery scoped to external boundaries only
Mock or spy `Mockery::mock()` only for external-boundary collaborators (AI/LLM gateway, Apify/scraper providers, Redis) in feature tests. Never mock internal repositories or services — exercise the real chain instead, and if a table lacks a migration forcing a repository stub, document why in the test file.

## Assert JSON by path
Assert response fields with `assertJsonPath()`. Use `assertExactJson()` only for a full-payload contract. Do not use fluent `AssertableJson`.
