#!/usr/bin/env bash
# Scale the app tier. Usage: scripts/scale.sh <replicas>   |   scripts/scale.sh load <workers> [think_ms]
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "load" ]]; then
  WORKERS="${2:?workers required}" THINK_MS="${3:-0}" docker compose up -d --no-deps --force-recreate loadgen
elif [[ "${1:-}" =~ ^[0-9]+$ ]]; then
  docker compose up -d --no-recreate --scale app="$1"
else
  echo "usage: $0 <replicas> | $0 load <workers> [think_ms]"; exit 1
fi
