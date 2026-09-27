#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=${1:-"$(dirname -- "$script_dir")"}
backup_dir=${2:-"$project_dir/backups"}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
database_name="gateway-$timestamp.db"

mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
cd "$project_dir"

docker compose exec -T api python -c \
  'import sqlite3; source = sqlite3.connect("/data/gateway.db"); target = sqlite3.connect("/data/gateway.backup.db"); source.backup(target); target.close(); source.close()'
docker compose cp api:/data/gateway.backup.db "$backup_dir/$database_name"
docker compose exec -T api python -c \
  'from pathlib import Path; Path("/data/gateway.backup.db").unlink(missing_ok=True)'

chmod 600 "$backup_dir/$database_name"
if [ -f .env ]; then
  cp .env "$backup_dir/env-$timestamp"
  chmod 600 "$backup_dir/env-$timestamp"
fi

echo "$backup_dir/$database_name"
