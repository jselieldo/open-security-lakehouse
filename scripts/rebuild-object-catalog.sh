#!/usr/bin/env bash
set -euo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository"

docker compose run --rm --no-deps api python -m app.object_catalog_backfill
