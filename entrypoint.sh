#!/bin/bash
set -e

MOUNT_PATH="${RAILWAY_VOLUME_MOUNT_PATH:-/data}"
DB_PATH="$MOUNT_PATH/personalAk_database.db"

if [ ! -f "$DB_PATH" ]; then
  mkdir -p "$(dirname "$DB_PATH")"
  cp /tmp/personalAk_database.db "$DB_PATH"
fi

export DB_PATH="$DB_PATH"
python main.py 