#!/usr/bin/env bash
set -e
# Every run migrates and truncates the shared test database named in .env.
: "${DB_DATABASE:=app_test}"
psql "$DB_DATABASE" -c "TRUNCATE exports" >/dev/null
psql "$DB_DATABASE" -f schema.sql >/dev/null
python3 verify.py
