import os
import aiosqlite

# Используем volume Railway (или локальный файл) через переменную окружения
DATABASE_URL = os.getenv('DB_PATH', '/app/telegram_videogame_bot/seed/personalAk_database.db')

async def init_db():
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                gender TEXT,
                age INTEGER,
                city TEXT,
                photos TEXT,
                favorite_games TEXT,
                description TEXT,
                profile_link TEXT,
                display_status TEXT DEFAULT 'нет',
                preferred_gender TEXT DEFAULT 'нейтральный',
                likes TEXT DEFAULT ''
            )
        ''')
        await db.commit()

async def add_user(user_id, username, gender, age, city, photos, favorite_games, description, profile_link, display_status='нет', preferred_gender='нейтральный', likes=''):
    photos_string = ','.join(photos)  # Сериализация списка фотографий в строку
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute('''
            INSERT INTO users (user_id, username, gender, age, city, photos, favorite_games, description, profile_link, display_status, preferred_gender, likes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, gender, age, city, photos_string, favorite_games, description, profile_link, display_status, preferred_gender, likes))
        await db.commit()

async def update_user(user_id, column, value):
    if column == 'photos' and isinstance(value, list):
        value = ','.join(value)
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(f"UPDATE users SET {column} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

async def get_user(user_id):
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = await cursor.fetchone()
            if user:
                user = list(user)
                user[5] = user[5].split(',') if user[5] else []  # Десериализация строки в список фотографий
            return user
    except Exception as e:
        print(f"Database error: {e}")
        return None