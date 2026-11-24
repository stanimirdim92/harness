#!/usr/bin/env bash
# Reconcile dependencies with tracked lockfiles, including incomplete installs.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
fail() { echo "worktree setup: $*" >&2; exit 1; }
BUILD=0
case "${1:-}" in
  '') [[ $# = 0 ]] || fail "usage: bin/worktree-setup.sh [--build]" ;;
  --build) [[ $# = 1 ]] || fail "usage: bin/worktree-setup.sh [--build]"; BUILD=1 ;;
  *) fail "usage: bin/worktree-setup.sh [--build]" ;;
esac
bin/worktree-doctor.sh --infrastructure
for file in .env .env.testing composer.lock yarn.lock; do
  [[ -f "$file" ]] || fail "$file is missing; copy ignored env files explicitly for manual worktrees"
done
for command in php composer node flock; do
  command -v "$command" >/dev/null || fail "missing $command"
done
if command -v corepack >/dev/null; then
  YARN=(corepack yarn)
elif command -v yarn >/dev/null; then
  YARN=(yarn)
else
  fail "missing Yarn; install Corepack or the Yarn version pinned in package.json"
fi
NODE_VERSION="$(node -p 'process.versions.node')"
IFS=. read -r MAJOR MINOR _ <<< "$NODE_VERSION"
[[ "$MAJOR" =~ ^[0-9]+$ && "$MINOR" =~ ^[0-9]+$ ]] || fail "unrecognized Node version: $NODE_VERSION"
(( (MAJOR == 20 && MINOR >= 19) || (MAJOR == 22 && MINOR >= 12) || MAJOR > 22 )) || fail "Node $NODE_VERSION does not meet Vite 8 requirements; select Node 20.19+ (20.x) or 22.12+ before setup/build"
# PHP, not Bash, expands $argv.
# shellcheck disable=SC2016
CHECKOUT_HASH="$(php -r 'echo substr(hash("sha256", $argv[1]), 0, 20);' "$ROOT")"
LOCK_DIR="/tmp/leadbuster-tests-$(id -u)"
if [[ ! -e "$LOCK_DIR" ]]; then mkdir -m 700 -- "$LOCK_DIR"; fi
[[ -d "$LOCK_DIR" && -O "$LOCK_DIR" && ! -L "$LOCK_DIR" ]] || fail "unsafe lock directory"
exec 9>"$LOCK_DIR/$CHECKOUT_HASH.lock"
flock -n 9 || fail "another setup, schema refresh, or test run is active in this checkout"
for directory in vendor node_modules node_modules/.bin public/build; do
  [[ ! -L "$directory" ]] || fail "$directory must belong to this checkout, not be a shared symlink"
done

# Do not boot providers using the normal local .env during dependency installation.
# Composer still generates autoload files. Laravel rebuilds missing manifests on boot.
composer install --no-interaction --prefer-dist --no-scripts
for manifest in bootstrap/cache/packages.php bootstrap/cache/services.php; do
  [[ ! -L "$manifest" ]] || fail "refusing a symlinked Laravel manifest"
  rm -f -- "$manifest"
done

YARN_VERSION="$("${YARN[@]}" --version)"
case "$YARN_VERSION" in
  1.*) "${YARN[@]}" install --frozen-lockfile ;;
  [2-9].*|[1-9][0-9].*) "${YARN[@]}" install --immutable ;;
  *) fail "unrecognized Yarn version: $YARN_VERSION" ;;
esac
if (( BUILD )); then
  "${YARN[@]}" run build
  bin/worktree-doctor.sh --frontend
else
  bin/worktree-doctor.sh
fi
echo "worktree dependencies ready: $(basename "$ROOT")"
for command in mysql mysqldump; do
  command -v "$command" >/dev/null || echo "backend tests/schema refresh still require $command" >&2
done
