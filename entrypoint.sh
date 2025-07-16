#!/bin/bash
set -e

# Путь к базе в Volume
DB_PATH="/data/personalAk_database.db"

# Если базы нет в Volume — копируем из /tmp (куда её положит Dockerfile)
if [ ! -f "$DB_PATH" ]; then
  mkdir -p $(dirname "$DB_PATH")
  cp /tmp/personalAk_database.db "$DB_PATH"
fi

# Запуск бота
export DB_PATH="$DB_PATH"
python telegram_videogame_bot/main.py 