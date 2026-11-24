---
paths:
    - 'Modules/*/app/Repositories/*.php'
---

# App Repositories

## Validate repository lookup columns

When `show()` accepts a column name, allow `id` and the model’s fillable columns. Reject other names before building the query.
