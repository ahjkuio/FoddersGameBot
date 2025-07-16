# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Копируем dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Копируем базу и entrypoint
COPY seed/personalAk_database.db /tmp/personalAk_database.db
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Указываем Volume (Railway сам смонтирует его в /data)
VOLUME ["/data"]

# Переходим внутрь директории бота
WORKDIR /app/telegram_videogame_bot

# Команда запуска
CMD ["/entrypoint.sh"] 