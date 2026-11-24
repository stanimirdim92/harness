#!/usr/bin/env bash
# Fixture checks of bin/worktree-test.sh. A stub Pest and stub PHP helpers stand in for the real
# ones, so no database, Redis connection or test run starts. The runner takes its lock
# files from the real lock directory, under names that belong to the fixture checkout only.
# Each check runs in its own subshell, so one failure does not hide the others.
set -euo pipefail
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
FIXTURE="$(mktemp -d /tmp/lb-runner-fixture.XXXXXXXX)"
CHECKOUT="$FIXTURE/checkout"
MOCKS="$FIXTURE/commands"
export OUT="$FIXTURE/pest-output"
export PIDS="$FIXTURE/pids"
REAL_PHP="$(command -v php)"
export REAL_PHP
LOCK_DIR="/tmp/leadbuster-tests-$(id -u)"
if [[ ! -e "$LOCK_DIR" ]]; then mkdir -m 700 -- "$LOCK_DIR"; fi
mkdir -p "$CHECKOUT/bin" "$CHECKOUT/vendor/bin" "$CHECKOUT/database/schema" "$MOCKS"
: > "$PIDS"
fail() { echo "FAIL: $*" >&2; exit 1; }

cleanup() {
  local hash pid
  # PHP, not Bash, expands $argv.
  # shellcheck disable=SC2016
  hash="$(php -r 'echo substr(hash("sha256", $argv[1]), 0, 20);' "$CHECKOUT")"
  while read -r _ pid _; do
    kill -9 "$pid" 2>/dev/null || true
  done < "$PIDS"
  rm -f -- "$LOCK_DIR/$hash.lock" "$LOCK_DIR"/leadbuster_tpl_aaaaaaaaaaaa_*.lock
  chmod -R u+rwx "$FIXTURE" 2>/dev/null || true
  rm -rf -- "$FIXTURE"
}
trap cleanup EXIT

cp "$SOURCE/bin/worktree-test.sh" "$CHECKOUT/bin/worktree-test.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$CHECKOUT/bin/worktree-doctor.sh"
chmod +x "$CHECKOUT/bin/worktree-test.sh" "$CHECKOUT/bin/worktree-doctor.sh"
touch "$CHECKOUT/vendor/autoload.php" "$CHECKOUT/.env.testing" "$CHECKOUT/phpunit.xml"
printf 'CREATE TABLE t (id INT);\n' > "$CHECKOUT/database/schema/mysql-schema.sql"
printf '%s\n' "$(printf 'a%.0s' {1..64})" > "$CHECKOUT/database/schema/mysql-schema.fingerprint"
sha256sum "$CHECKOUT/database/schema/mysql-schema.sql" | cut -d' ' -f1 > "$CHECKOUT/database/schema/mysql-schema.sql.sha256"

# The helpers that need a database succeed without one; PHP, not Bash, expands $argv.
cat > "$MOCKS/php" <<'SH'
#!/usr/bin/env bash
case "${1:-}" in
  -r) exec "$REAL_PHP" "$@" ;;
  bin/worktree-databases.php|bin/schema-snapshot.php) exit 0 ;;
  *) echo "unexpected php call: $*" >&2; exit 99 ;;
esac
SH
cat > "$MOCKS/mktemp" <<'SH'
#!/usr/bin/env bash
directory="$(/usr/bin/mktemp "$@")"
if [[ "${MKTEMP_READ_ONLY:-}" = 1 ]]; then chmod 500 "$directory"; fi
printf '%s' "$directory" > "${MKTEMP_RECORD:-/dev/null}"
printf '%s\n' "$directory"
SH

# The stub records what the runner passes to Pest. STUB_MODE picks its behaviour:
# record (default), hang (wait for a signal), server (leave a Playwright-like process behind),
# server-hang (start a Playwright-like process, then wait for a signal).
cat > "$CHECKOUT/vendor/bin/pest" <<'SH'
#!/usr/bin/env bash
{
  printf 'args=%s\n' "$*"
  env | sort | grep -E '^(DB_|REDIS_|APP_|LB_TEST_RUNTIME|PHP_INI_SCAN_DIR)' || true
  if [[ -f "$LB_TEST_RUNTIME/pcov.ini" ]]; then sed 's/^/pcov.ini: /' "$LB_TEST_RUNTIME/pcov.ini"; fi
} > "$OUT"
case "${STUB_MODE:-record}" in
  hang)
    printf 'pest %s %s\n' "$$" "$LB_TEST_RUNTIME" >> "$PIDS"
    exec sleep 300 ;;
  server)
    (exec -a 'node playwright run-server' sleep 300) &
    printf 'own-server %s\n' "$!" >> "$PIDS" ;;
  server-hang)
    (exec -a 'node playwright run-server' sleep 300) &
    printf 'orphan-server %s\n' "$!" >> "$PIDS"
    printf 'orphan-pest %s %s\n' "$$" "$LB_TEST_RUNTIME" >> "$PIDS"
    exec sleep 300 ;;
esac
SH
chmod +x "$MOCKS/"* "$CHECKOUT/vendor/bin/pest"

run_runner() {
  env PATH="$MOCKS:$PATH" "$CHECKOUT/bin/worktree-test.sh" "$@"
}
expect_output() {
  if ! grep -Fq -- "$1" "$OUT"; then
    cat "$OUT" >&2
    fail "$2: expected '$1' in the stub Pest output"
  fi
}
expect_no_output() {
  if grep -Fq -- "$1" "$OUT"; then
    cat "$OUT" >&2
    fail "$2: did not expect '$1' in the stub Pest output"
  fi
}
wait_until() {
  local _
  for _ in {1..50}; do
    if "$@"; then return 0; fi
    sleep 0.1
  done
  return 1
}
has_pcov() { php -r 'exit(extension_loaded("pcov") ? 0 : 1);'; }

check_database_variables_come_from_env_testing() {
  env DB_HOST=caller-host DB_PORT=1 DB_SOCKET=/caller.sock DB_USERNAME=caller DB_PASSWORD=caller DB_URL=mysql://caller DB_CHARSET=caller DATABASE_URL=mysql://caller REDIS_HOST=10.0.0.9 REDIS_PORT=1 REDIS_URL=redis://caller \
    PATH="$MOCKS:$PATH" "$CHECKOUT/bin/worktree-test.sh" tests/Unit/ExampleTest.php > /dev/null
  local variable
  for variable in DB_HOST DB_PORT DB_SOCKET DB_USERNAME DB_PASSWORD DB_URL DB_CHARSET DATABASE_URL REDIS_HOST REDIS_PORT REDIS_URL; do
    expect_no_output "$variable=" "the caller's $variable"
  done
  expect_output 'DB_CONNECTION=mysql' 'the runner sets the connection'
  expect_output 'DB_DATABASE=leadbuster_test_' 'the runner sets the checkout database'
}

check_bootstrap_caches_are_redirected() {
  run_runner tests/Unit/ExampleTest.php > /dev/null
  local line runtime
  line="$(grep '^LB_TEST_RUNTIME=' "$OUT")"
  runtime="${line#LB_TEST_RUNTIME=}"
  expect_output "APP_ROUTES_CACHE=$runtime/routes.php" 'routes cache redirect'
  expect_output "APP_EVENTS_CACHE=$runtime/events.php" 'events cache redirect'
  expect_output "APP_CONFIG_CACHE=$runtime/config.php" 'config cache redirect'
}

check_parallel_options_are_rejected() {
  local option
  for option in --parallel --parallel=2 -p -p4; do
    if run_runner "$option" tests/Unit/ExampleTest.php > "$FIXTURE/rejected" 2>&1; then
      fail "the runner accepted $option"
    fi
    if ! grep -Fq "unsupported override: $option" "$FIXTURE/rejected"; then
      cat "$FIXTURE/rejected" >&2
      fail "the runner did not explain why it rejected $option"
    fi
  done
  if run_runner --mutate --covered-only -p tests/Unit/ExampleTest.php > "$FIXTURE/rejected" 2>&1; then
    fail 'the mutation runner accepted -p'
  fi
  for option in tests ./tests/ tests/Browser --testsuite=Unit,Browser; do
    if run_runner --mutate --covered-only "$option" > "$FIXTURE/rejected" 2>&1; then
      fail "the mutation runner accepted $option"
    fi
    if ! grep -Fq -- "--mutate must not run the Browser suite; drop $option" "$FIXTURE/rejected"; then
      cat "$FIXTURE/rejected" >&2
      fail "the mutation runner did not explain why it rejected $option"
    fi
  done
}

check_coverage_options_load_pcov_for_the_checkout() {
  has_pcov || { echo 'SKIP: pcov is not loaded' >&2; return 0; }
  local option
  for option in --coverage-text=/tmp/lb-runner-coverage.txt --coverage-html=/tmp/lb-runner-coverage --coverage-clover=/tmp/lb-runner-clover.xml --coverage; do
    run_runner "$option" --only-summary-for-coverage-text tests/Unit/ExampleTest.php > /dev/null
    expect_output "pcov.ini: pcov.directory=$CHECKOUT" "PCOV directory for $option"
    expect_output 'pcov.ini: pcov.enabled=1' "PCOV enabled for $option"
    expect_output 'PHP_INI_SCAN_DIR=' "the scan directory for $option"
  done
  run_runner tests/Unit/ExampleTest.php > /dev/null
  expect_no_output 'pcov.directory' 'a run without a coverage option'
}

check_value_taking_options_do_not_hide_a_full_suite() {
  exec 8>"$LOCK_DIR/full-suite.1.lock"
  if ! flock -n 8; then echo 'SKIP: full-suite slot 1 is in use by another run' >&2; return 0; fi
  local arguments
  for arguments in '--processes 2' '--processes=2' '--shard 1/2' '--log-junit /tmp/lb-runner.xml'; do
    # shellcheck disable=SC2086
    LB_FULL_SUITE_SLOTS=1 timeout 3 env PATH="$MOCKS:$PATH" "$CHECKOUT/bin/worktree-test.sh" $arguments > /dev/null 2> "$FIXTURE/waiting" || true
    if ! grep -Fq 'waiting for a full-suite slot' "$FIXTURE/waiting"; then
      cat "$FIXTURE/waiting" >&2
      fail "a full suite started with '$arguments' did not wait for a slot"
    fi
  done
  for arguments in '--processes 2 tests/Unit/ExampleTest.php' 'tests/Unit/ExampleTest.php --processes 2' '--filter=Example'; do
    # shellcheck disable=SC2086
    LB_FULL_SUITE_SLOTS=1 timeout 10 env PATH="$MOCKS:$PATH" "$CHECKOUT/bin/worktree-test.sh" $arguments > /dev/null 2> "$FIXTURE/waiting" || fail "the focused run '$arguments' did not finish"
    if grep -Fq 'waiting for a full-suite slot' "$FIXTURE/waiting"; then
      fail "the focused run '$arguments' waited for a slot"
    fi
  done
}

check_runtime_directory_does_not_leak() {
  [[ "$(id -u)" != 0 ]] || { echo 'SKIP: root can write to a read-only directory' >&2; return 0; }
  export MKTEMP_RECORD="$FIXTURE/mktemp-record"
  if env MKTEMP_READ_ONLY=1 PATH="$MOCKS:$PATH" "$CHECKOUT/bin/worktree-test.sh" tests/Unit/ExampleTest.php > /dev/null 2>&1; then
    fail 'the runner succeeded although it could not write to its runtime directory'
  fi
  local leaked
  leaked="$(< "$MKTEMP_RECORD")"
  if [[ -e "$leaked" ]]; then
    chmod u+rwx "$leaked"
    rm -rf -- "$leaked"
    fail "the runner leaked $leaked"
  fi
}

check_cleanup_stops_only_its_own_playwright_server() {
  (cd "$CHECKOUT" && exec -a 'node playwright run-server' sleep 300) &
  local foreign="$!" own
  printf 'foreign-server %s\n' "$foreign" >> "$PIDS"
  STUB_MODE=server run_runner tests/Unit/ExampleTest.php > /dev/null
  own="$(awk '$1 == "own-server" {print $2}' "$PIDS")"
  [[ -n "$own" ]] || fail 'the stub left no Playwright server behind'
  # shellcheck disable=SC2329  # wait_until calls it by name
  stopped() { ! kill -0 "$own" 2>/dev/null || [[ "$(ps -o stat= -p "$own" | tr -d ' ')" = Z ]]; }
  wait_until stopped || fail 'the runner left the Playwright server of its own run'
  kill -0 "$foreign" 2>/dev/null || fail 'the runner stopped a Playwright server that it did not start'
}

check_pest_dies_with_the_runner() {
  # A SIGKILL of the runner releases its locks. An orphaned Pest would then share the worker
  # databases with the next run.
  STUB_MODE=hang env PATH="$MOCKS:$PATH" "$CHECKOUT/bin/worktree-test.sh" --filter=Example tests/Unit/ExampleTest.php > /dev/null 2>&1 &
  local runner="$!" pest runtime
  # shellcheck disable=SC2329  # wait_until calls it by name
  pest_started() { grep -q '^pest ' "$PIDS"; }
  wait_until pest_started || fail 'the runner never started Pest'
  pest="$(awk '$1 == "pest" {print $2}' "$PIDS")"
  runtime="$(awk '$1 == "pest" {print $3}' "$PIDS")"
  kill -9 "$runner"
  wait "$runner" 2>/dev/null || true
  # shellcheck disable=SC2329  # wait_until calls it by name
  pest_stopped() { ! kill -0 "$pest" 2>/dev/null; }
  if ! wait_until pest_stopped; then
    rm -rf -- "$runtime"
    fail 'an orphaned Pest survived the death of the runner'
  fi
  rm -rf -- "$runtime"
}

check_next_run_stops_the_server_of_a_killed_run() {
  # A SIGKILL of the runner skips its cleanup, and Pest dies without stopping its Playwright
  # server. The next run must stop that server and remove the runtime directory.
  STUB_MODE=server-hang env PATH="$MOCKS:$PATH" "$CHECKOUT/bin/worktree-test.sh" --filter=Example tests/Unit/ExampleTest.php > /dev/null 2>&1 &
  local runner="$!" pest server runtime
  # shellcheck disable=SC2329  # wait_until calls it by name
  pest_started() { grep -q '^orphan-pest ' "$PIDS"; }
  wait_until pest_started || fail 'the runner never started Pest'
  pest="$(awk '$1 == "orphan-pest" {print $2}' "$PIDS")"
  server="$(awk '$1 == "orphan-server" {print $2}' "$PIDS")"
  runtime="$(awk '$1 == "orphan-pest" {print $3}' "$PIDS")"
  kill -9 "$runner"
  wait "$runner" 2>/dev/null || true
  # shellcheck disable=SC2329  # wait_until calls it by name
  pest_stopped() { ! kill -0 "$pest" 2>/dev/null; }
  wait_until pest_stopped || fail 'Pest survived the death of the runner'
  kill -0 "$server" 2>/dev/null || fail 'the fixture server stopped before the next run'
  run_runner tests/Unit/ExampleTest.php > /dev/null
  # shellcheck disable=SC2329  # wait_until calls it by name
  stopped() { ! kill -0 "$server" 2>/dev/null || [[ "$(ps -o stat= -p "$server" | tr -d ' ')" = Z ]]; }
  if ! wait_until stopped; then
    rm -rf -- "$runtime"
    fail 'the next run left the Playwright server of the killed run'
  fi
  if [[ -e "$runtime" ]]; then
    rm -rf -- "$runtime"
    fail 'the next run left the runtime directory of the killed run'
  fi
}

PASSED=0
FAILED=()
for check in check_database_variables_come_from_env_testing check_bootstrap_caches_are_redirected \
  check_parallel_options_are_rejected check_coverage_options_load_pcov_for_the_checkout \
  check_value_taking_options_do_not_hide_a_full_suite check_runtime_directory_does_not_leak \
  check_cleanup_stops_only_its_own_playwright_server check_pest_dies_with_the_runner \
  check_next_run_stops_the_server_of_a_killed_run; do
  if ( "$check" ); then
    PASSED=$((PASSED + 1))
  else
    FAILED+=("$check")
  fi
done
printf 'worktree runner: %s checks passed, %s failed\n' "$PASSED" "${#FAILED[@]}"
if (( ${#FAILED[@]} > 0 )); then
  printf 'failed: %s\n' "${FAILED[@]}" >&2
  exit 1
fi
