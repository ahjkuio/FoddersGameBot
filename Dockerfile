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

# Копируем исходники
COPY . .

# Команда запуска
CMD ["python", "-m", "telegram_videogame_bot.main"] 