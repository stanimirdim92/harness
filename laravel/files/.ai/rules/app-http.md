---
paths:
    - 'app/Http/**'
---

# App Http

## Validate input before reading typed values

Build service DTOs from validated Form Request data. For scalar fields read directly by an HTTP action, validate first and then use the typed getter. Read raw input when the original value or the distinction between missing and explicit values matters.
