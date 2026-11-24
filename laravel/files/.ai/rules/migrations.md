---
paths:
  - 'Modules/*/database/migrations/*.php'
---

# Migrations

## Write real down() logic
Always implement a genuine reverse migration in `down()`, guarding column/table drops with `Schema::hasColumn`/`hasTable` checks where the `up()` logic was itself conditional.

## Store enums as string/int + PHP enum cast
Never use the DB `enum()` column type. Store enum values as `string()`/`tinyInteger()`/`unsignedTinyInteger()` and cast to a PHP backed enum on the model.

## Path-scoped FK style
Inside `Modules/*/database/migrations`, declare FK-like columns as plain `unsignedBigInteger()->index()`. Never `->constrained()`, `->foreign()`, or `foreignIdFor()` — that style belongs only to root/vendor-origin migrations, a different population.
