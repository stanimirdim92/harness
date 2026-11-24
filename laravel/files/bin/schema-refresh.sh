#!/usr/bin/env bash
# Reads leadbuster; publishes the snapshot and safely rebuilds its own template.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
# PHP, not Bash, expands $argv.
# shellcheck disable=SC2016
CHECKOUT_HASH="$(php -r 'echo substr(hash("sha256", $argv[1]), 0, 20);' "$ROOT")"
LOCK_DIR="/tmp/leadbuster-tests-$(id -u)"
if [[ ! -e "$LOCK_DIR" ]]; then mkdir -m 700 -- "$LOCK_DIR"; fi
[[ -d "$LOCK_DIR" && -O "$LOCK_DIR" && ! -L "$LOCK_DIR" ]] || exit 1
exec 9>"$LOCK_DIR/$CHECKOUT_HASH.lock"
flock -n 9 || { echo "A test run or schema refresh is active in this checkout" >&2; exit 1; }
# bin/schema-snapshot.php locks the new snapshot's own template
# (leadbuster_tpl_<fingerprint>_<checksum>) like a test run: shared, plus the build
# lock when the template is missing. It keeps an existing template of that name, so a
# test run of another checkout never blocks it. Templates of other snapshots are never touched.
exec php bin/schema-snapshot.php refresh
