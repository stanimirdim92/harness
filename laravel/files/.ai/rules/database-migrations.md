---
paths:
  - 'database/migrations/*.php'
---

# Database Migrations

## Write real down() logic
Always implement a genuine reverse migration in `down()`, guarding column/table drops with `Schema::hasColumn`/`hasTable` checks where the `up()` logic was itself conditional.
Use plain SQL whenever possible. It's faster to understand and can be copy pasted
