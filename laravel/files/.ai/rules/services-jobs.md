---
paths:
  - 'Modules/*/app/{Services,Jobs}/**/*.php'
---

# Services Jobs

## Inject dependencies, don't service-locate
Use constructor injection in Services and typed `handle()` parameters in Jobs. Reserve `app()`/`resolve()` only for genuine runtime-dynamic class selection.
