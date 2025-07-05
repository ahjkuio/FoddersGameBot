# FoddersGameBot

Телеграм-бот для геймеров: новости, цены, база игр и сервис знакомств.

## Быстрый деплой на Railway

1. Зарегистрируйтесь на [railway.app](https://railway.app/).
2. Нажмите «New Project» → «Deploy from GitHub» и выберите репозиторий с ботом.
3. Railway автоматически обнаружит `Dockerfile` и соберёт контейнер.
4. В разделе **Variables** добавьте переменные окружения:
   - `BOT_TOKEN` — токен Telegram-бота
   - `STEAM_API_KEY` — ключ Steam Web API
   - `ITAD_API_KEY` — (по желанию) ключ IsThereAnyDeal API
   - `ADMIN_CHAT_ID` — ID вашего telegram-аккаунта для логов
5. Нажмите **Deploy**. Через 1-2 минуты бот запустится. В логе появится:
   ```text
   Игровой Бот запущен и готов к работе!
   ```
6. Убедитесь, что бот ответил на команду `/start`.

### Локальный запуск через Docker
```
docker build -t foddersbot .
docker run -d --name foddersbot \
  -e BOT_TOKEN=xxxxxxxxxx \
  -e STEAM_API_KEY=yyyyyyyy \
  foddersbot
```

> По умолчанию используется Python 3.12-slim и long-polling. 