---
paths:
    - 'app/**/*.php'
---

# App 2

## Prefer the existing data type for simple transformations

For simple transformations, prefer collection methods on collections and `array_map()` on arrays. Use `foreach` for branching, early exit, or explicit key handling. Convert to a collection when its operations make the code clearer. Treat this as guidance when editing existing loops.
