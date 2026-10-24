#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for category in path command sql; do
  for variant in buggy fixed; do
    .venv/bin/safety-harness run "data/controlled/$category-01/$variant.py" \
      "data/controlled/$category-01/reference.py" --category "$category" \
      --out "results/reproduced/$category-$variant.json"
  done
done
