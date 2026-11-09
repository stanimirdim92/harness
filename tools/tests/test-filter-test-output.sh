#!/usr/bin/env bash
# Fixture tests for claude/hooks/filter-test-output.sh (ADR 0123).
#
# Each case feeds the hook a PostToolUse input for one Bash command and checks
# whether it replaced the output. The negative cases matter as much: a failing
# run, a short run, a piped command and a command that only mentions a runner
# must keep their full output.
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../claude/hooks" && pwd)/filter-test-output.sh"
command -v jq >/dev/null || { echo "test-filter-test-output: jq is required" >&2; exit 1; }
PASS=0; FAIL=0

lines() {   # lines N [LAST]: N progress lines, then LAST as the final line
  seq 1 "$1" | sed 's/^/  ✓ test case /'
  [ -n "${2:-}" ] && printf '%s\n' "$2"
}
run() {     # run COMMAND STDOUT [STDERR]: print the hook's JSON output, if any
  jq -n --arg c "$1" --arg o "$2" --arg e "${3:-}" \
    '{tool_name:"Bash", tool_input:{command:$c},
      tool_response:{stdout:$o, stderr:$e, interrupted:false, isImage:false}}' | "$HOOK"
}
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }
expect_kept() {   # expect_kept NAME COMMAND STDOUT [STDERR]
  local got; got="$(run "$2" "$3" "${4:-}")"
  [ -z "$got" ] && ok || bad "$1: output was replaced"
}
expect_short() {  # expect_short NAME COMMAND STDOUT [STDERR]: stdout is shortened
  local got; got="$(run "$2" "$3" "${4:-}")"
  if [ -z "$got" ]; then bad "$1: output was kept"; return; fi
  local o; o="$(printf '%s' "$got" | jq -r '.hookSpecificOutput.updatedToolOutput.stdout')"
  printf '%s' "$o" | grep -q 'lines hidden' || { bad "$1: no notice line"; return; }
  [ "$(printf '%s\n' "$o" | wc -l)" -le 61 ] || { bad "$1: too long"; return; }
  ok
}

pass="$(lines 300 'Tests: 300 passed (600 assertions)')"

# Runners at command position are shortened.
expect_short 'artisan test'      'php artisan test'                     "$pass"
expect_short 'env prefix'        'DB_DATABASE=x php artisan test'       "$pass"
expect_short 'phpunit'           'vendor/bin/phpunit --testdox'         "$pass"
expect_short 'pest'              './vendor/bin/pest'                    "$pass"
expect_short 'vitest'            'npx vitest run'                       "$pass"
expect_short 'npm test'          'npm test'                             "$pass"
expect_short 'pnpm run test'     'pnpm run test -- --reporter=verbose'  "$pass"
expect_short 'pytest'            'python -m pytest -v'                  "$pass"
expect_short 'after cd'          'cd app && php artisan test'           "$pass"
expect_short 'merged streams'    'php artisan test 2>&1'                "$pass"

# The summary and the warnings survive.
got="$(run 'php artisan test' "$(lines 10; echo '  ! WARN deprecated helper'; lines 300 'Tests: 310 passed')")"
o="$(printf '%s' "$got" | jq -r '.hookSpecificOutput.updatedToolOutput.stdout')"
printf '%s' "$o" | grep -q 'Tests: 310 passed' && ok || bad 'summary kept'
printf '%s' "$o" | grep -q 'WARN deprecated helper' && ok || bad 'warning kept'

# The other fields of the Bash result are copied, not dropped.
got="$(run 'npm test' "$pass")"
[ "$(printf '%s' "$got" | jq -c '.hookSpecificOutput.updatedToolOutput | [.interrupted, .isImage]')" = '[false,false]' ] \
  && ok || bad 'result shape kept'

# Jest writes its report to stderr; that stream is shortened too.
got="$(run 'npx jest' 'ok' "$pass")"
printf '%s' "$got" | jq -r '.hookSpecificOutput.updatedToolOutput.stderr' | grep -q 'lines hidden' \
  && ok || bad 'stderr shortened'

# ANSI colour codes do not hide a failure.
expect_kept 'coloured failure'   'npx vitest run'  "$(lines 300 $'\e[31mTests  1 failed\e[0m | 299 passed')"

# Failing runs keep everything.
expect_kept 'pest failed'        'php artisan test'   "$(lines 300 'Tests: 2 failed, 298 passed')"
expect_kept 'phpunit failures'   'vendor/bin/phpunit' "$(lines 300 'FAILURES!')"
expect_kept 'pytest failed'      'pytest'             "$(lines 300 '=== 1 failed, 299 passed ===')"
expect_kept 'jest FAIL'          'npx jest'           "$(echo 'FAIL src/a.test.ts'; lines 300)"
expect_kept 'traceback'          'pytest'             "$(echo 'Traceback (most recent call last):'; lines 300)"

# Zero failures is still a pass.
expect_short 'zero failed'       'pytest'  "$(lines 300 '=== 300 passed, 0 failed, 0 errors ===')"

# Short output, piped output and non-runners are left alone.
expect_kept 'short run'          'php artisan test'          "$(lines 100 'Tests: 100 passed')"
expect_kept 'piped'              'php artisan test | tail'   "$pass"
expect_kept 'redirected'         'npm test > out.log'        "$pass"
expect_kept 'quoted mention'     'echo "php artisan test"'   "$pass"
expect_kept 'grep mention'       'grep -r pytest docs/'      "$pass"
expect_kept 'other artisan'      'php artisan test:seed'     "$pass"
expect_kept 'other npm script'   'npm run testing'           "$pass"

# An interrupted run is left alone.
got="$(jq -n --arg o "$pass" '{tool_input:{command:"npm test"},
  tool_response:{stdout:$o, stderr:"", interrupted:true, isImage:false}}' | "$HOOK")"
[ -z "$got" ] && ok || bad 'interrupted'

echo "test-filter-test-output: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
