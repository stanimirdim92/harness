#!/usr/bin/env bash
# Fixture checks: never install dependencies or touch databases in a real checkout.
set -euo pipefail
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
FIXTURE="$(mktemp -d /tmp/lb-readiness.XXXXXXXX)"
trap 'rm -rf -- "$FIXTURE"' EXIT
MAIN="$FIXTURE/main checkout"
TICKET="$FIXTURE/external ticket"
MOCKS="$FIXTURE/commands"
ORIGINAL_PATH="$PATH"
REAL_NODE="$(command -v node)"
export REAL_NODE
export FIXTURE_LOG="$FIXTURE/installs.log"
export XDG_RUNTIME_DIR="$FIXTURE/runtime"
mkdir -p "$MAIN/bin" "$MAIN/app/Support" "$MAIN/tests" "$MOCKS" "$XDG_RUNTIME_DIR"
cp "$SOURCE/bin/worktree-doctor.sh" "$SOURCE/bin/worktree-setup.sh" "$MAIN/bin/"
# The version steps below start from 2, independent of the real runtime version.
printf '2\n' > "$MAIN/bin/worktree-runtime.version"
for file in bin/schema-snapshot.php bin/worktree-databases.php app/Support/WorktreeTesting.php app/Support/TestSchema.php app/Support/WorktreeDatabaseRegistry.php tests/bootstrap.php; do
  printf 'fixture\n' > "$MAIN/$file"
done
printf '#!/bin/bash\nbin/worktree-doctor.sh --infrastructure\n' > "$MAIN/bin/worktree-test.sh"
chmod +x "$MAIN/bin/worktree-test.sh"
git -C "$MAIN" init -q -b main
git -C "$MAIN" add .
git -C "$MAIN" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm initial
git -C "$MAIN" worktree add -qb fixture "$TICKET"
PASSED=0
expect_success() {
  local label="$1"; shift
  if ! "$@" > "$FIXTURE/output" 2>&1; then
    cat "$FIXTURE/output" >&2
    echo "FAIL: $label" >&2
    exit 1
  fi
  PASSED=$((PASSED + 1))
}
expect_failure() {
  local label="$1" message="$2"; shift 2
  if "$@" > "$FIXTURE/output" 2>&1; then
    echo "FAIL: $label unexpectedly passed" >&2
    exit 1
  fi
  if ! grep -Fq -- "$message" "$FIXTURE/output"; then
    cat "$FIXTURE/output" >&2
    echo "FAIL: $label did not explain $message" >&2
    exit 1
  fi
  PASSED=$((PASSED + 1))
}
DOCTOR="$TICKET/bin/worktree-doctor.sh"
expect_success 'external worktree with spaces and matching runtime' "$DOCTOR" --infrastructure
printf '3\n' > "$MAIN/bin/worktree-runtime.version"
expect_failure 'newer canonical working tree' 'older than main runtime 3' "$DOCTOR" --infrastructure
printf '3\n' > "$TICKET/bin/worktree-runtime.version"
expect_success 'newer ticket runtime' "$DOCTOR" --infrastructure
printf '4\n' > "$MAIN/bin/worktree-runtime.version"
git -C "$MAIN" add bin/worktree-runtime.version
git -C "$MAIN" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm version4
printf '2\n' > "$MAIN/bin/worktree-runtime.version"
expect_failure 'committed main cannot be hidden by older working copy' 'older than main runtime 4' "$DOCTOR" --infrastructure
printf '4\n' > "$TICKET/bin/worktree-runtime.version"
expect_success 'ticket matches committed main' "$DOCTOR" --infrastructure
printf 'invalid\n' > "$TICKET/bin/worktree-runtime.version"
expect_failure 'invalid version' 'invalid runtime version' "$DOCTOR" --infrastructure
rm "$TICKET/bin/worktree-runtime.version"
expect_failure 'missing version' 'runtime version missing' "$DOCTOR" --infrastructure
printf '4\n' > "$TICKET/bin/worktree-runtime.version"
printf 'old runner\n' > "$TICKET/bin/worktree-test.sh"
expect_failure 'version-only update cannot hide old runner' 'lacks the infrastructure guard' "$DOCTOR" --infrastructure
cp "$MAIN/bin/worktree-test.sh" "$TICKET/bin/worktree-test.sh"
rm "$TICKET/app/Support/TestSchema.php"
expect_failure 'incomplete runtime' 'TestSchema.php is missing' "$DOCTOR" --infrastructure
cp "$MAIN/app/Support/TestSchema.php" "$TICKET/app/Support/TestSchema.php"
chmod -x "$TICKET/bin/worktree-test.sh"
expect_failure 'non-executable runtime' 'worktree-test.sh is not executable' "$DOCTOR" --infrastructure
chmod +x "$TICKET/bin/worktree-test.sh"
mkdir "$FIXTURE/infra-commands"
ln -s "$(command -v git)" "$FIXTURE/infra-commands/git"
ln -s "$(command -v dirname)" "$FIXTURE/infra-commands/dirname"
expect_success 'infrastructure requires no PHP Node or dependencies' env PATH="$FIXTURE/infra-commands" /bin/bash "$DOCTOR" --infrastructure

cat > "$MOCKS/node" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" = -p && "${2:-}" = process.versions.node ]]; then
  echo "${FIXTURE_NODE_VERSION:-22.12.0}"
else
  exec "$REAL_NODE" "$@"
fi
SH
cat > "$MOCKS/composer" <<'SH'
#!/usr/bin/env bash
set -eu
printf 'composer %s\n' "$*" >> "$FIXTURE_LOG"
[[ "$*" = 'install --no-interaction --prefer-dist --no-scripts' ]]
mkdir -p vendor
touch vendor/autoload.php
SH
cat > "$MOCKS/corepack" <<'SH'
#!/usr/bin/env bash
set -eu
printf 'corepack %s\n' "$*" >> "$FIXTURE_LOG"
case "$*" in
  'yarn --version') echo 4.18.0 ;;
  'yarn install --immutable')
    mkdir -p node_modules/.bin
    for binary in vite tsc eslint vitest; do
      printf '#!/bin/sh\nexit 0\n' > "node_modules/.bin/$binary"
      chmod +x "node_modules/.bin/$binary"
    done ;;
  'yarn run build')
    mkdir -p public/build/assets
    printf 'built\n' > public/build/assets/app.js
    printf '{"app":{"file":"assets/app.js"}}\n' > public/build/manifest.json ;;
  *) exit 1 ;;
esac
SH
chmod +x "$MOCKS/"*
export PATH="$MOCKS:$ORIGINAL_PATH"
mkdir -p "$TICKET/bootstrap/cache"
touch "$TICKET/.env" "$TICKET/.env.testing" "$TICKET/composer.lock" "$TICKET/yarn.lock"
expect_failure 'missing dependencies diagnosed' 'Composer dependencies missing' "$DOCTOR"
expect_success 'setup reconciles existing checkout without requiring assets' "$TICKET/bin/worktree-setup.sh"
grep -Fq 'composer install --no-interaction --prefer-dist --no-scripts' "$FIXTURE_LOG"
grep -Fq 'corepack yarn install --immutable' "$FIXTURE_LOG"
if grep -Fq 'corepack yarn run build' "$FIXTURE_LOG"; then
  echo 'setup without --build ran a build' >&2
  exit 1
fi
expect_success 'normal doctor permits no build until needed' "$DOCTOR"
# shellcheck disable=SC2016 # $argv is PHP, not shell.
HASH="$(php -r 'echo substr(hash("sha256", $argv[1]), 0, 20);' "$TICKET")"
grep -Fq "leadbuster_test_$HASH (default workers: half the CPU count)" "$FIXTURE/output"
expect_failure 'browser verification requires a build' 'build manifest missing' "$DOCTOR" --frontend
mkdir -p "$TICKET/public/build/assets"
printf '{"app":{"file":"assets/app.js","css":["assets/app.css"]}}\n' > "$TICKET/public/build/manifest.json"
expect_failure 'manifest alone cannot claim ready' 'missing or invalid asset: assets/app.js' "$DOCTOR"
touch "$TICKET/public/build/assets/app.js"
expect_failure 'missing CSS diagnosed' 'missing or invalid asset: assets/app.css' "$DOCTOR" --frontend
touch "$TICKET/public/build/assets/app.css"
expect_success 'complete manifest assets' "$DOCTOR" --frontend
printf '{"app":{"file":"assets/app.js","imports":["missing"]}}\n' > "$TICKET/public/build/manifest.json"
expect_failure 'manifest references require matching entries' 'missing manifest import' "$DOCTOR" --frontend
printf 'not json\n' > "$TICKET/public/build/manifest.json"
expect_failure 'invalid manifest diagnosed' 'run bin/worktree-setup.sh --build' "$DOCTOR" --frontend
expect_success 'explicit build repairs incomplete copied assets' "$TICKET/bin/worktree-setup.sh" --build
grep -Fq 'corepack yarn run build' "$FIXTURE_LOG"
rm "$TICKET/node_modules/.bin/vite"
expect_failure 'missing copied executable diagnosed' 'node_modules/.bin/vite missing' "$DOCTOR"
expect_success 'setup repairs missing copied executable' "$TICKET/bin/worktree-setup.sh"
INSTALL_COUNT="$(grep -c 'composer install' "$FIXTURE_LOG")"
[[ "$INSTALL_COUNT" = 3 ]] || { echo 'FAIL: setup skipped a dependency reconciliation' >&2; exit 1; }
expect_failure 'unsupported Node stops setup before installing' 'does not meet Vite 8 requirements' env FIXTURE_NODE_VERSION=20.15.1 "$TICKET/bin/worktree-setup.sh"
[[ "$(grep -c 'composer install' "$FIXTURE_LOG")" = "$INSTALL_COUNT" ]]
expect_failure 'Node 21 is unsupported' 'does not meet Vite 8 requirements' env FIXTURE_NODE_VERSION=21.7.0 "$DOCTOR"
expect_success 'Node 20 supported floor' env FIXTURE_NODE_VERSION=20.19.0 "$DOCTOR"
expect_success 'Node 24 supported' env FIXTURE_NODE_VERSION=24.0.0 "$DOCTOR"
mv "$TICKET/node_modules" "$FIXTURE/shared-dependencies"
ln -s "$FIXTURE/shared-dependencies" "$TICKET/node_modules"
expect_failure 'shared dependencies rejected before install' 'not be a shared symlink' "$TICKET/bin/worktree-setup.sh"
expect_failure 'unknown setup flags rejected' 'usage:' "$TICKET/bin/worktree-setup.sh" --wrong
printf 'worktree readiness: %s fixture checks passed\n' "$PASSED"
