## Ticket

LD-

## What changed

<!-- One or two sentences: the result, then the reason. -->

## How it was verified

- [ ] `composer test -- --filter=...`
- [ ] `yarn test` / `yarn build`
- [ ] Checked in the browser (if UI)

## Checklist

- [ ] Schema change: migration added and `bin/schema-refresh.sh` snapshot files committed together
- [ ] New env/config keys added to `.env.example`
- [ ] EN and DE translation keys updated together
- [ ] No existing UI control, route or permission removed without approval
- [ ] Deploy notes below (migrations, queues/Horizon restart, cache clear, backfill commands)

## Deploy notes

<!-- "None" if a plain deploy is enough. -->
