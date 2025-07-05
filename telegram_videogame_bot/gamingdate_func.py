from personalAccount_DB import get_user, update_user
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
import logging

DATABASE_URL = 'personalAk_database.db'

async def find_potential_friends(user_data, viewed_users):
    user_id, username, gender, age, city, photos, favorite_games, description, profile_link, display_status, preferred_gender, likes = user_data
    
    async with aiosqlite.connect(DATABASE_URL) as db:
        cursor = await db.execute('''
            SELECT * FROM users WHERE user_id != ? AND display_status = 'да'
        ''', (user_id,))
        all_users = await cursor.fetchall()

    def filter_users(users, criteria):
        filtered = []
        for user in users:
            if user[0] not in viewed_users and all(criterion(user) for criterion in criteria):
                filtered.append(user)
        return filtered
    
    def gender_match(user):
        if preferred_gender == 'нейтральный':
            return True
        elif preferred_gender == 'мужской':
            return user[2].lower() == 'мужской'
        elif preferred_gender == 'женский':
            return user[2].lower() == 'женский'
        return False
    
    def age_match(user):
        return user[3] is not None and abs(user[3] - age) <= 4
    
    def city_match(user):
        return user[4] == city
    
    def games_match(user):
        user_games = set(user[6].split(',')) if user[6] else set()
        my_games = set(favorite_games.split(','))
        return bool(my_games & user_games)  # Проверка на пересечение множеств
    
    def always_true(user):
        return True

    # Уровни совпадений
    criteria_list = [
        [gender_match, age_match, city_match, games_match],
        [gender_match, age_match, city_match],
        [gender_match, age_match],
        [gender_match],
        [age_match, city_match, games_match],
        [age_match, city_match],
        [age_match],
        [city_match, games_match],
        [city_match],
        [games_match],
        [always_true]
    ]

    prioritized_users = []
    for criteria in criteria_list:
        filtered_users = filter_users(all_users, criteria)
        if filtered_users:
            prioritized_users.extend(filtered_users)
            all_users = [user for user in all_users if user not in filtered_users]

    return prioritized_users

async def add_like(user_id, liked_user_id):
    user_data = await get_user(liked_user_id)
    if user_data:
        likes = user_data[-1]  # Последний элемент - likes
        likes_list = likes.split(',') if likes else []
        if str(user_id) not in likes_list:
            likes_list.append(str(user_id))
            likes_string = ','.join(likes_list)
            await update_user(liked_user_id, "likes", likes_string)

async def send_notification(bot: Bot, user_id: int, message: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Посмотреть GDate'ы", callback_data="view_gdates")],
        [InlineKeyboardButton(text="Не сейчас", callback_data="dismiss")]
    ])
    await bot.send_message(user_id, message, reply_markup=keyboard)


async def get_likes(user_id):
    user_data = await get_user(user_id)
    likes = user_data[-1]  # Последний элемент - likes
    likes_list = likes.split(',') if likes else []
    return likes_list

async def remove_like(user_id, liked_user_id):
    user_data = await get_user(user_id)
    likes = user_data[-1]  # Последний элемент - likes
    likes_list = likes.split(',') if likes else []
    if str(liked_user_id) in likes_list:
        likes_list.remove(str(liked_user_id))
        likes_string = ','.join(likes_list)
        await update_user(user_id, "likes", likes_string)