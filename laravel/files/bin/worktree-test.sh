#!/usr/bin/env bash
# Canonical backend test entry point. Requires PHP with phpredis, flock and the shared local Redis server.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"

fail() { echo "worktree tests: $*" >&2; exit 1; }
bin/worktree-doctor.sh --infrastructure

# Alternate bootstraps / configurations can remove the guard. Keep test selectors
# and ordinary PHPUnit/Pest options, but reject runtime/configuration overrides.
for argument in "$@"; do
  case "$argument" in
    --env|--env=*|--configuration|--configuration=*|-c|-c?*|--bootstrap|--bootstrap=*|--no-configuration|--parallel|--parallel=*|-p|-p?*|--without-databases|--runner|--runner=*|--php-binary|--php-binary=*|-d|-d?*)
      fail "unsupported override: $argument" ;;
  esac
done
unset TEST_TOKEN UNIQUE_TEST_TOKEN LARAVEL_PARALLEL_TESTING
# The caller's database and Redis settings must not beat .env.testing: bin/schema-snapshot.php and
# bin/worktree-databases.php read .env.testing alone, and so must the workers.
while IFS= read -r name; do unset "$name"; done < <(compgen -e | grep -E '^(DB_|REDIS_|DATABASE_URL$)' || true)

# Type coverage reads the source list in phpunit.xml and exits before PHPUnit.
for argument in "$@"; do
  if [[ "$argument" = --type-coverage ]]; then
    for option in "$@"; do
      case "$option" in
        --type-coverage|--compact|--no-cache|--min=*|--memory-limit=*|--type-coverage-json=*|--shard=*|--colors=*) ;;
        *) fail "unsupported option for --type-coverage: $option" ;;
      esac
    done
    exec vendor/bin/pest "$@"
  fi
done

# The profanity scan reads the source list in phpunit.xml and exits before PHPUnit.
for argument in "$@"; do
  if [[ "$argument" = --profanity ]]; then
    for option in "$@"; do
      case "$option" in
        --profanity|--compact|--language=*|--include=*|--exclude=*|--output=*|--colors=*) ;;
        *) fail "unsupported option for --profanity: $option" ;;
      esac
    done
    exec vendor/bin/pest "$@"
  fi
done

for command in php flock timeout setpriv; do
  command -v "$command" >/dev/null || fail "missing $command"
done
php -r 'exit(extension_loaded("redis") ? 0 : 1);' || fail "missing the phpredis PHP extension"
[[ -f vendor/autoload.php && -f .env.testing && -f phpunit.xml ]] || fail "run bin/worktree-setup.sh first; .env.testing and phpunit.xml are required"
[[ -s database/schema/mysql-schema.sql && -s database/schema/mysql-schema.fingerprint ]] || fail "missing schema snapshot; run bin/schema-refresh.sh"
[[ -s database/schema/mysql-schema.sql.sha256 ]] || fail "snapshot needs the new checksum; run bin/schema-refresh.sh once"

# --mutate runs Pest's mutation testing as one worker. Pest's parallel mode
# scores a mutant as killed when its child process fails for any reason
# (pestphp/pest#2018), and each child here needs a worker database.
MUTATE=0
for argument in "$@"; do
  case "$argument" in
    --mutate) MUTATE=1 ;;
  esac
done
if [[ "$MUTATE" = 1 ]]; then
  for argument in "$@"; do
    case "$argument" in
      --processes|--processes=*) fail "--mutate runs as one worker; drop $argument" ;;
      --everything) fail "--everything makes Pest ignore --class; name the classes with --class only" ;;
      # Each mutant's child run would start its own Playwright server and leave it running.
      tests|tests/|./tests|./tests/|tests/Browser*|./tests/Browser*|--testsuite=*Browser*)
        fail "--mutate must not run the Browser suite; drop $argument (the default suites are Unit,Feature)" ;;
    esac
  done
  php -r 'exit(extension_loaded("pcov") ? 0 : 1);' || fail "--mutate needs the pcov PHP extension"
fi

# PCOV guesses app/ as its directory, which leaves out Modules/. Cover the whole checkout instead.
use_checkout_pcov() {
  printf 'pcov.enabled=1\npcov.directory=%s\npcov.exclude="~/(vendor|node_modules|tests)/~"\n' "$ROOT" > "$LB_TEST_RUNTIME/pcov.ini"
  PHP_INI_SCAN_DIR="$(php -r 'echo PHP_CONFIG_FILE_SCAN_DIR;'):$LB_TEST_RUNTIME"
  export PHP_INI_SCAN_DIR
}

# Each checkout gets its own database, so worktrees run independently and
# concurrently. LB_SCHEMA_TEMPLATE is the shared, read-only source they clone
# their tables from (see App\Support\WorktreeTesting).
# PHP, not Bash, expands $argv.
# shellcheck disable=SC2016
CHECKOUT_HASH="$(php -r 'echo substr(hash("sha256", $argv[1]), 0, 20);' "$ROOT")"
[[ "$CHECKOUT_HASH" =~ ^[a-f0-9]{20}$ ]] || fail "cannot identify checkout"
export LB_TEST_DATABASE="leadbuster_test_${CHECKOUT_HASH}"

LOCK_DIR="/tmp/leadbuster-tests-$(id -u)"
if [[ ! -e "$LOCK_DIR" ]]; then mkdir -m 700 -- "$LOCK_DIR"; fi
[[ -d "$LOCK_DIR" && -O "$LOCK_DIR" && ! -L "$LOCK_DIR" ]] || fail "unsafe lock directory"

# Per-checkout: prevents this checkout's own setup/refresh/test-run from racing.
exec 9>"$LOCK_DIR/$CHECKOUT_HASH.lock"
flock -n 9 || fail "another backend test run, setup, or schema refresh is active in this checkout"
php bin/worktree-databases.php --register "$ROOT"

EXPECTED_SQL_HASH="$(tr -d '[:space:]' < database/schema/mysql-schema.sql.sha256)"
# PHP, not Bash, expands $argv.
# shellcheck disable=SC2016
ACTUAL_SQL_HASH="$(php -r 'echo hash_file("sha256", $argv[1]);' database/schema/mysql-schema.sql)"
[[ "$EXPECTED_SQL_HASH" =~ ^[a-f0-9]{64}$ && "$EXPECTED_SQL_HASH" = "$ACTUAL_SQL_HASH" ]] || fail "schema SQL checksum mismatch; run bin/schema-refresh.sh"
RECORDED="$(tr -d '[:space:]' < database/schema/mysql-schema.fingerprint)"
[[ "$RECORDED" =~ ^[a-f0-9]{64}$ ]] || fail "invalid schema fingerprint; run bin/schema-refresh.sh"

# A full suite takes one of LB_FULL_SUITE_SLOTS machine-wide slots (default 3).
# Parallel sessions otherwise run several four-worker suites on the same CPUs
# and slow every run, focused ones included. A path, --filter, --group,
# --testsuite or --mutate makes the run focused; a focused run never waits.
FULL_SUITE=1
VALUE_NEXT=0
for argument in "$@"; do
  # The word after an option that needs a value is that value, not a test path.
  if [[ "$VALUE_NEXT" = 1 ]]; then VALUE_NEXT=0; continue; fi
  case "$argument" in
    --processes|--shard|--log-junit|--log-teamcity|--coverage-clover|--coverage-html|--coverage-xml|--coverage-cobertura|--coverage-crap4j|--coverage-php) VALUE_NEXT=1 ;;
    --filter*|--group*|--testsuite*|--mutate) FULL_SUITE=0 ;;
    -*) ;;
    *) FULL_SUITE=0 ;;
  esac
done
if [[ "$FULL_SUITE" = 1 ]]; then
  SLOTS="${LB_FULL_SUITE_SLOTS:-3}"
  [[ "$SLOTS" =~ ^[1-9][0-9]?$ ]] || fail "LB_FULL_SUITE_SLOTS must be 1-99"
  SLOT=""
  while [[ -z "$SLOT" ]]; do
    for ((slot = 1; slot <= SLOTS; slot++)); do
      exec 5>"$LOCK_DIR/full-suite.$slot.lock"
      if flock -n 5; then SLOT="$slot"; break; fi
    done
    if [[ -z "$SLOT" ]]; then
      [[ -n "${WAITING:-}" ]] || echo "waiting for a full-suite slot: $SLOTS full suites already run on this machine" >&2
      WAITING=1
      sleep 5
    fi
  done
fi

# One template per committed snapshot, built from mysql-schema.sql alone, never
# from the live leadbuster database. The name holds the schema fingerprint and
# the checksum of the SQL file: the fingerprint ignores comments, table options
# and migration rows. A ticket that changes the snapshot gets its own template;
# other checkouts keep theirs. TestSchema::snapshotTemplateName() builds the
# same name.
export LB_SCHEMA_TEMPLATE="leadbuster_tpl_${RECORDED:0:12}_${ACTUAL_SQL_HASH:0:12}"
# Shared (reader) lock for the whole run: any number of checkouts may clone this
# template at once. bin/schema-refresh.sh and bin/worktree-databases.php need the
# exclusive (writer) lock to rebuild or drop it.
exec 7>"$LOCK_DIR/$LB_SCHEMA_TEMPLATE.lock"
flock -s -w 30 7 || fail "timed out waiting for a schema refresh or cleanup of $LB_SCHEMA_TEMPLATE"
if ! php bin/schema-snapshot.php template-check; then
  # Builders serialise on a separate lock, so a waiting builder never blocks on
  # the shared lock of a run that already uses the template. template-build
  # checks again before it imports and verifies the fingerprint after.
  exec 6>"$LOCK_DIR/$LB_SCHEMA_TEMPLATE.build.lock"
  flock -x -w 300 6 || fail "timed out waiting for another run to build $LB_SCHEMA_TEMPLATE"
  php bin/schema-snapshot.php template-build || fail "cannot build $LB_SCHEMA_TEMPLATE from database/schema/mysql-schema.sql"
  exec 6>&-
fi

# Prints the start time of a process, so a reused process ID never passes as the original.
process_start() {
  local stat
  stat="$(cat -- "/proc/$1/stat" 2>/dev/null)" || return 1
  read -ra stat <<< "${stat##*) }"
  printf '%s' "${stat[19]}"
}
# A SIGKILL of a runner skips its cleanup, and its Pest dies without stopping its
# Playwright server. Stop each server whose runner is gone: its runtime directory is
# missing, or the owner file in it names a process that no longer runs. A directory
# without an owner file belongs to an older runner and is left alone.
stop_orphaned_playwright_servers() {
  local pid runtime owner start
  for pid in $(pgrep -u "$(id -u)" -f 'playwright run-server' || true); do
    runtime="$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | sed -n 's/^LB_TEST_RUNTIME=//p')"
    [[ "$runtime" == /tmp/lb-test.* ]] || continue
    if [[ -d "$runtime" ]]; then
      read -r owner start < "$runtime/owner" 2>/dev/null || continue
      [[ "$(process_start "$owner")" != "$start" ]] || continue
    fi
    kill -- "$pid" 2>/dev/null || true
    rm -rf -- "$runtime"
  done
}
stop_orphaned_playwright_servers

LB_TEST_RUNTIME=""
cleanup() {
  local status=$? process environment
  [[ -n "$LB_TEST_RUNTIME" ]] || return "$status"
  # Pest's browser plugin keeps its Playwright server for reuse, and a parallel
  # run never stops it. Stop the servers that this run started in this checkout:
  # they inherited LB_TEST_RUNTIME. A server of another origin is left alone.
  for process in /proc/[0-9]*; do
    [[ "$(readlink -- "$process/cwd" 2>/dev/null)" = "$ROOT" ]] || continue
    if tr '\0' ' ' < "$process/cmdline" 2>/dev/null | grep -q 'playwright run-server'; then
      environment="$(tr '\0' '\n' < "$process/environ" 2>/dev/null || true)"
      if grep -qxF "LB_TEST_RUNTIME=$LB_TEST_RUNTIME" <<< "$environment"; then
        kill -- "${process#/proc/}" 2>/dev/null || true
      fi
    fi
  done
  rm -rf -- "$LB_TEST_RUNTIME"
  return "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# The traps come first: a failure between mktemp and the end of setup must not leak the directory.
LB_TEST_RUNTIME="$(mktemp -d /tmp/lb-test.XXXXXXXXXX)"
export LB_TEST_RUNTIME
printf '%s' "$ROOT" > "$LB_TEST_RUNTIME/checkout"
printf '%s %s\n' "$$" "$(process_start "$$")" > "$LB_TEST_RUNTIME/owner"

export APP_ENV=testing DB_CONNECTION=mysql DB_DATABASE="$LB_TEST_DATABASE"
# Ignore any local application config, route and event cache without deleting it.
export APP_CONFIG_CACHE="$LB_TEST_RUNTIME/config.php"
export APP_ROUTES_CACHE="$LB_TEST_RUNTIME/routes.php" APP_EVENTS_CACHE="$LB_TEST_RUNTIME/events.php"
export CACHE_STORE=array SESSION_DRIVER=array MAIL_MAILER=array
export APP_MAINTENANCE_DRIVER=file TELESCOPE_ENABLED=false PULSE_ENABLED=false

# Default to half the CPU count, split evenly between this run and every
# other checkout that holds its test lock (a test run, setup or schema refresh),
# with at least one worker: several agents testing at once otherwise exhaust
# CPU and RAM. /proc/locks is read, never the lock itself, so a starting run is
# never blocked. Pass --processes=N to select the worker count for this run.
OTHER_RUNS=0
for lock in "$LOCK_DIR"/*.lock; do
  [[ "$(basename -- "$lock")" =~ ^[a-f0-9]{20}\.lock$ && "$lock" != "$LOCK_DIR/$CHECKOUT_HASH.lock" ]] || continue
  read -r major minor inode < <(stat -c '%Hd %Ld %i' -- "$lock")
  if grep -q " $(printf '%02x:%02x:%s' "$major" "$minor" "$inode") " /proc/locks; then OTHER_RUNS=$((OTHER_RUNS + 1)); fi
done
CPUS="$(nproc)"
WORKERS=$(( CPUS / 2 / (OTHER_RUNS + 1) ))
if (( WORKERS < 1 )); then WORKERS=1; fi
PROCESSES=(--processes="$WORKERS")
for argument in "$@"; do
  case "$argument" in
    --processes|--processes=*) PROCESSES=() ;;
  esac
done

echo "test database namespace: $LB_TEST_DATABASE"
(( ${#PROCESSES[@]} == 0 )) || echo "workers: $WORKERS ($OTHER_RUNS other checkout test runs active)"
# Pest dies with this script: after a SIGKILL of the script its locks are gone, and an
# orphaned Pest would share the worker databases with the next run.
PEST=(setpriv --pdeathsig=KILL vendor/bin/pest)
if [[ "$MUTATE" = 1 ]]; then
  # One worker database (token 1), shared in turn by every mutant's child run.
  use_checkout_pcov
  TEST_TOKEN=1 LARAVEL_PARALLEL_TESTING=1 "${PEST[@]}" "$@" 5>&- 6>&- 7>&- 9>&-
  exit
fi
# --tia records and replays Pest's test impact graph from PCOV coverage, and a
# coverage option measures it, so both need the checkout-wide pcov.directory that
# --mutate uses. --tia fails without PCOV. A coverage option falls back to Xdebug.
for argument in "$@"; do
  case "$argument" in
    --tia)
      php -r 'exit(extension_loaded("pcov") ? 0 : 1);' || fail "--tia needs the pcov PHP extension"
      use_checkout_pcov ;;
    --coverage|--coverage=*|--coverage-*)
      if php -r 'exit(extension_loaded("pcov") ? 0 : 1);'; then use_checkout_pcov; fi ;;
  esac
done
# Pest runs directly, not through `php artisan test`: Collision validates every
# option against ParaTest and rejects Pest-only options such as --ci and --shard.
# These are the runner, configuration and environment Collision would pass.
# The lock descriptors stay with this script: a process that outlives Pest must
# not keep the checkout or template locked.
LARAVEL_PARALLEL_TESTING=1 "${PEST[@]}" --parallel "${PROCESSES[@]}" \
  --configuration="$ROOT/phpunit.xml" --runner='\Illuminate\Testing\ParallelRunner' "$@" 5>&- 6>&- 7>&- 9>&-
