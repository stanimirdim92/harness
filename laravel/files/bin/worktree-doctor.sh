#!/usr/bin/env bash
# Read-only readiness check. Infrastructure mode needs only Bash and Git.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
fail() { echo "worktree doctor: $*" >&2; exit 1; }
MODE="${1:-}"
[[ $# -le 1 && ( -z "$MODE" || "$MODE" = --infrastructure || "$MODE" = --frontend ) ]] || fail "usage: bin/worktree-doctor.sh [--infrastructure|--frontend]"

command -v git >/dev/null || fail "Git is required to identify the checkout"
COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir)" || fail "cannot identify the canonical checkout"
[[ "$COMMON_DIR" = */.git ]] || fail "a non-bare canonical checkout is required"
CANONICAL="${COMMON_DIR%/.git}"
[[ -d "$CANONICAL" ]] || fail "canonical checkout is unavailable: $CANONICAL"
VERSION_FILE=bin/worktree-runtime.version
read_version() {
  local value="$1"
  [[ "$value" =~ ^[1-9][0-9]{0,5}$ ]] || fail "invalid runtime version: $value"
  printf '%s' "$value"
}
[[ -f "$VERSION_FILE" ]] || fail "runtime version missing; integrate current main infrastructure first"
VERSION="$(read_version "$(< "$VERSION_FILE")")"
REQUIRED=0
if [[ -f "$CANONICAL/$VERSION_FILE" ]]; then
  REQUIRED="$(read_version "$(< "$CANONICAL/$VERSION_FILE")")"
fi
git rev-parse --verify refs/heads/main >/dev/null 2>&1 || fail "local main ref is unavailable; restore the project baseline before dispatch"
if COMMITTED="$(git show "refs/heads/main:$VERSION_FILE" 2>/dev/null)"; then
  COMMITTED="$(read_version "$COMMITTED")"
  (( COMMITTED <= REQUIRED )) || REQUIRED="$COMMITTED"
fi
(( VERSION >= REQUIRED )) || fail "runtime $VERSION is older than main runtime $REQUIRED; integrate current main infrastructure into this branch before setup/tests"
for file in bin/worktree-test.sh bin/worktree-setup.sh bin/schema-snapshot.php bin/worktree-databases.php app/Support/WorktreeTesting.php app/Support/TestSchema.php app/Support/WorktreeDatabaseRegistry.php tests/bootstrap.php; do
  [[ -s "$file" ]] || fail "runtime $VERSION is incomplete: $file is missing"
done
for script in bin/worktree-test.sh bin/worktree-setup.sh; do
  [[ -x "$script" ]] || fail "runtime $VERSION is incomplete: $script is not executable"
done
RUNNER="$(< bin/worktree-test.sh)"
[[ "$RUNNER" = *'bin/worktree-doctor.sh --infrastructure'* ]] || fail "test runner lacks the infrastructure guard; integrate the complete runtime change from main"
printf 'infrastructure: runtime %s (main requires %s)\n' "$VERSION" "$REQUIRED"
[[ "$MODE" != --infrastructure ]] || exit 0

ERRORS=0
problem() { echo "NOT READY: $*" >&2; ERRORS=1; }
printf 'checkout: %s\nbranch: %s\n' "$ROOT" "$(git branch --show-current)"
if command -v php >/dev/null; then
  # PHP, not Bash, expands $argv.
  # shellcheck disable=SC2016
  CHECKOUT_HASH="$(php -r 'echo substr(hash("sha256", $argv[1]), 0, 20);' "$ROOT")"
  printf 'test database: leadbuster_test_%s (default workers: half the CPU count)\n' "$CHECKOUT_HASH"
  if php -r 'exit(extension_loaded("pcov") ? 0 : 1);'; then
    echo 'coverage: pcov loaded (pest --mutate can run)'
  else
    PHP_MINOR="$(php -r 'echo PHP_MAJOR_VERSION, ".", PHP_MINOR_VERSION;')"
    problem "PHP extension pcov missing; mutation testing (pest --mutate) needs it. Install: sudo apt install php${PHP_MINOR}-pcov"
  fi
else
  problem "PHP missing; test namespace could not be calculated"
fi
for file in .env .env.testing composer.lock yarn.lock; do
  [[ -f "$file" ]] || problem "$file missing; run bin/worktree-setup.sh after copying checkout env files"
done
for directory in vendor node_modules node_modules/.bin public/build; do
  [[ ! -L "$directory" ]] || problem "$directory must be owned by this checkout, not a shared symlink"
done
[[ -f vendor/autoload.php ]] || problem "Composer dependencies missing; run bin/worktree-setup.sh"
for binary in vite tsc eslint vitest; do
  [[ -x "node_modules/.bin/$binary" ]] || problem "node_modules/.bin/$binary missing; run bin/worktree-setup.sh"
done
echo 'dependencies: presence checked; setup reconciles them with current lockfiles'
NODE_READY=0
if command -v node >/dev/null; then
  NODE_VERSION="$(node -p 'process.versions.node')"
  IFS=. read -r MAJOR MINOR _PATCH <<< "$NODE_VERSION"
  if [[ "$MAJOR" =~ ^[0-9]+$ && "$MINOR" =~ ^[0-9]+$ ]] && (( (MAJOR == 20 && MINOR >= 19) || (MAJOR == 22 && MINOR >= 12) || MAJOR > 22 )); then
    NODE_READY=1
    printf 'Node: %s\n' "$NODE_VERSION"
  else
    problem "Node $NODE_VERSION does not meet Vite 8 requirements; select Node 20.19+ (20.x) or 22.12+ before setup/build"
  fi
else
  problem "Node missing; select Node 20.19+ (20.x) or 22.12+ before setup/build"
fi
if command -v corepack >/dev/null; then
  echo 'Yarn: available through corepack yarn (project packageManager)'
elif command -v yarn >/dev/null; then
  echo 'Yarn: available through yarn'
else
  problem "Yarn missing; install Corepack or the Yarn version pinned in package.json"
fi

if [[ ! -f public/build/manifest.json ]]; then
  if [[ "$MODE" = --frontend ]]; then
    problem "build manifest missing; run bin/worktree-setup.sh --build before browser verification"
  else
    echo 'browser assets: not built; run bin/worktree-setup.sh --build when needed'
  fi
elif (( NODE_READY )); then
  if ! node --input-type=commonjs <<'NODE'
const fs = require('node:fs');
const path = require('node:path');
try {
  const base = path.resolve('public/build');
  const manifest = JSON.parse(fs.readFileSync(path.join(base, 'manifest.json'), 'utf8'));
  if (!manifest || Array.isArray(manifest) || typeof manifest !== 'object' || !Object.keys(manifest).length) {
    throw new Error('manifest must contain build entries');
  }
  let files = new Set();
  for (const [key, entry] of Object.entries(manifest)) {
    if (!entry || typeof entry.file !== 'string') throw new Error(`invalid entry: ${key}`);
    for (const field of ['css', 'assets', 'imports', 'dynamicImports']) {
      if (entry[field] !== undefined && (!Array.isArray(entry[field]) || entry[field].some(value => typeof value !== 'string'))) {
        throw new Error(`invalid ${field}: ${key}`);
      }
    }
    for (const imported of [...(entry.imports || []), ...(entry.dynamicImports || [])]) {
      if (!Object.hasOwn(manifest, imported)) throw new Error(`missing manifest import: ${imported}`);
    }
    for (const file of [entry.file, ...(entry.css || []), ...(entry.assets || [])]) {
      const resolved = path.resolve(base, file);
      if (!resolved.startsWith(base + path.sep) || !fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
        throw new Error(`missing or invalid asset: ${file}`);
      }
      files.add(file);
    }
  }
  console.log(`browser assets: ${files.size} manifest files present (rebuild after source changes)`);
} catch (error) {
  console.error(`NOT READY: ${error.message}; run bin/worktree-setup.sh --build`);
  process.exit(1);
}
NODE
  then
    ERRORS=1
  fi
fi
exit "$ERRORS"
