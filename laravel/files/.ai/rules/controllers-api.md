---
paths:
  - 'Modules/{Socials,Core}/app/Http/Controllers/Api/**'
---

# Controllers Api

## Use Resource classes for model-shaped responses
Wrap Eloquent models/collections returned from Socials and Core API endpoints in a dedicated JsonResource class instead of raw arrays.
