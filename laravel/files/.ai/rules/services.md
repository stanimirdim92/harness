---
paths:
  - 'Modules/*/app/Services/*.php'
---

# Services

## No shared Core base Service — module-local base services instead
Don't add a cross-module base Service to Core. When a module's services share behavior, extend a base service defined in that same module (see `BrightDataSocialsService`, `ApifyAPIService`, `AdvertiserService`).
