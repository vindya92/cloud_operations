#!/usr/bin/env bash
# Fault injection for incident practice. Usage: scripts/chaos.sh {errors|latency|down|up|reset}
set -euo pipefail
cd "$(dirname "$0")/.."
APP_URL=${APP_URL:-http://localhost:8000}

auth_curl() {
  local token
  token=$(docker compose exec -T app python -c \
    'from security import create_access_token; print(create_access_token("chaos-script"))')
  curl -sS -X POST "$APP_URL/chaos" -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' -d "$1"
}

case "${1:-}" in
  errors)  auth_curl '{"error_rate":0.4,"cause":"db_pool_exhausted"}' ;;
  latency) auth_curl '{"latency_ms":1500}' ;;
  down)    docker compose stop app ;;
  up)      docker compose start app ;;
  reset)   auth_curl '{}' ;;
  *) echo "usage: $0 {errors|latency|down|up|reset}"; exit 1 ;;
esac
echo
