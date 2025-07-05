from aiogram import types, Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from personalAccount_DB import get_user, add_user, update_user
from personalAccount_keyboards import personal_account_keyboard, edit_profile_keyboard, gender_keyboard, edit_gender_keyboard, confirm_profile_keyboard
from base_keyboards import reply_menu_keyboard
from functools import partial
from typing import Union

import asyncio
import logging




# Состояния
class PersonalAccount(StatesGroup):
    waiting_for_name = State()
    waiting_for_gender = State()
    waiting_for_custom_gender = State()
    waiting_for_age = State()
    waiting_for_city = State()
    waiting_for_photos = State()
    waiting_for_games = State()
    waiting_for_description = State()
    waiting_for_edit_choice = State()
    editing_name = State()
    editing_gender = State()
    editing_for_custom_gender = State()
    editing_age = State()
    editing_city = State()
    editing_photos = State()
    editing_games = State()
    editing_description = State()

async def personal_account_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await get_user(user_id)
    if user_data:
        await message.answer("Вы уже зарегистрированы.", reply_markup=reply_menu_keyboard)
        return
    await state.set_state(PersonalAccount.waiting_for_name)
    await message.answer("Привет, геймер! Давай создадим твой личный кабинет. Как тебя зовут (или твой ник)?", reply_markup=reply_menu_keyboard)

async def personal_account_name(message: types.Message, state: FSMContext):
    username = message.from_user.username
    profile_link = f"@{username}" if username else "Не указан"
    await state.update_data(username=message.text, profile_link=profile_link)
    await state.set_state(PersonalAccount.waiting_for_gender)
    await message.answer("Какой у тебя пол?", reply_markup=gender_keyboard())

async def personal_account_gender(call: types.CallbackQuery, state: FSMContext):
    if call.data == "gender:custom":
        await call.message.edit_text("Пожалуйста, напиши свой пол:")
        await state.set_state(PersonalAccount.waiting_for_custom_gender)
    else:
        data = await state.get_data()
        data['gender'] = "Мужской" if call.data == "gender:male" else "Женский"
        data['preferred_gender'] = 'нейтральный'  # Устанавливаем предпочтение по умолчанию
        await state.update_data(data)
        await state.set_state(PersonalAccount.waiting_for_age)
        await call.message.edit_text("Сколько тебе лет?")

async def personal_account_custom_gender(message: types.Message, state: FSMContext):
    await state.update_data(gender=message.text)
    await state.set_state(PersonalAccount.waiting_for_age)
    await message.answer("Сколько тебе лет?")

async def personal_account_age(message: types.Message, state: FSMContext):
    await state.update_data(age=int(message.text))
    await state.set_state(PersonalAccount.waiting_for_city)
    await message.answer("Из какого ты города? Это поможет найти игроков поблизости. Можешь написать реальный город или любой другой, если хочешь сохранить анонимность.")

async def personal_account_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(PersonalAccount.waiting_for_photos)
    await message.answer("Отправь мне до 5 фотографий. Отправь все за раз или напиши 'Пропустить', если не хочешь отправлять фото.")

async def personal_account_photos(message: types.Message, state: FSMContext):
    logger.info("Handling photo message...")
    current_state = await state.get_state()

    if current_state == 'PersonalAccount:waiting_for_games':
        logger.info("Already in waiting for games state, skipping...")
        return

    if message.text and message.text.lower() == 'пропустить':
        logger.info("Skip command received")
        await state.set_state(PersonalAccount.waiting_for_games)
        await message.answer("Какие у тебя любимые игры? Перечисли через запятую.")
        return

    if message.photo:
        photo_id = message.photo[-1].file_id  # ID последней фотографии
        logger.info(f"Received photo ID: {photo_id}")

        data = await state.get_data()
        current_photos = set(data.get('photos', []))
        logger.info(f"Current photos in state: {current_photos}")

        if photo_id not in current_photos:
            current_photos.add(photo_id)
            await state.update_data(photos=list(current_photos))
            logger.info("Photos updated in state.")

        # Запускаем или перезапускаем таймер
        if 'timer_handle' in data:
            data['timer_handle'].cancel()  # Отменяем предыдущий таймер, if он есть
        timer_callback = partial(set_waiting_for_games_state, message=message, state=state)
        timer_handle = asyncio.get_event_loop().call_later(3, lambda: asyncio.create_task(timer_callback()))
        await state.update_data(timer_handle=timer_handle)

    logger.info("Handling complete.")

async def set_waiting_for_games_state(message: types.Message, state: FSMContext):
    await state.set_state(PersonalAccount.waiting_for_games)
    logger.info("Moved to waiting for games state after timeout.")
    await message.answer("Какие у тебя любимые игры? Перечисли через запятую.")

async def personal_account_games(message: types.Message, state: FSMContext):
    await state.update_data(favorite_games=message.text)
    await state.set_state(PersonalAccount.waiting_for_description)
    await message.answer("Напиши что-нибудь о себе для описания в профиле.")

async def personal_account_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    profile_data = await state.get_data()
    await message.answer("Все готово! Вот что у нас получилось:")
    await send_profile_preview(message, profile_data)
    await message.answer("Если все верно, нажми 'Подтвердить'. Если нужно что-то изменить, нажми 'Изменить'.", reply_markup=confirm_profile_keyboard())

async def send_profile_preview(message: types.Message, data: dict):
    profile_text = (
        f"Имя: {data['username']}\n"
        f"Пол: {data['gender']}\n"
        f"Возраст: {data['age']}\n"
        f"Город: {data['city']}\n"
        f"Любимые игры: {data['favorite_games']}\n"
        f"Описание: {data['description']}\n"
    )

    if 'photos' in data and data['photos']:
        photos = data['photos']
        media = [types.InputMediaPhoto(media=photo) for photo in photos]
        if len(media) > 5:
            media = media[:5]
        await message.answer_media_group(media)
    await message.answer(profile_text)

async def confirm_profile(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await add_user(
        user_id=call.from_user.id,
        username=data['username'],
        gender=data['gender'],
        age=data['age'],
        city=data['city'],
        photos=data.get('photos', ''),
        favorite_games=data['favorite_games'],
        description=data['description'],
        profile_link=data['profile_link'],
        display_status='нет',
        preferred_gender=data.get('preferred_gender', 'нейтральный'),
        likes=''
    )
    await state.clear()
    await call.message.edit_text("Твой профиль создан! Используй команду /menu для доступа к основному меню.")

async def edit_profile(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("Что вы хотите изменить?", reply_markup=edit_profile_keyboard())
    await state.set_state(PersonalAccount.waiting_for_edit_choice)

async def handle_edit_choice(call: types.CallbackQuery, state: FSMContext):
    choice = call.data.split(':')[1]
    await state.update_data(editing=True)
    is_editing_from_menu = (await state.get_data()).get('editing_from_menu', False)

    state_map = {
        'name': (PersonalAccount.editing_name, "Введите новое имя:", None),
        'gender': (PersonalAccount.editing_gender, "Выберите новый пол:", edit_gender_keyboard()),
        'age': (PersonalAccount.editing_age, "Введите новый возраст:", None),
        'city': (PersonalAccount.editing_city, "Введите новый город:", None),
        'photos': (PersonalAccount.editing_photos, "Отправьте новые фотографии или напишите 'Пропустить':", None),
        'games': (PersonalAccount.editing_games, "Введите новые любимые игры:", None),
        'description': (PersonalAccount.editing_description, "Введите новое описание:", None)
    }

    target_state, prompt, keyboard = state_map.get(choice, (None, "Неизвестный выбор", None))

    if target_state is None:
        await call.message.answer("Неизвестный выбор. Пожалуйста, попробуйте снова.")
        return

    await call.message.edit_text(prompt, reply_markup=keyboard)
    await state.set_state(target_state)

    # if редактирование идет из меню, сразу отправляем обновленные данные в базу
    if is_editing_from_menu:
        await update_user_data(call.from_user.id, choice, state)  # Обновляем данные в базе

async def update_user_data(user_id: int, field: str, state: FSMContext):
    # Получаем данные из состояния
    data = await state.get_data()
    # Получаем новое значение для изменяемого поля
    value = data.get(field)
    # Если значение существует, обновляем базу данных
    if value:
        await update_user(user_id, field, value)

async def edit_name(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)
    await update_user_data(message.from_user.id, 'username', state)
    await show_updated_profile(message, state)  # Показываем обновленный профиль
    await state.clear()  # Сбрасываем состояние после показа профиля

async def edit_gender(call: types.CallbackQuery, state: FSMContext):
    if call.data == "edit_gender:custom":
        await call.message.edit_text("Пожалуйста, напишите свой пол:")
        await state.set_state(PersonalAccount.editing_for_custom_gender)
    else:
        data = await state.get_data()
        data['gender'] = "Мужской" if call.data == "edit_gender:male" else "Женский"
        await state.update_data(data)
        await update_user_data(call.from_user.id, 'gender', state)
        await show_updated_profile(call.message, state)  # Показываем обновленный профиль
        await state.clear()  # Сбрасываем состояние после показа профиля

async def edit_custom_gender(message: types.Message, state: FSMContext):
    await state.update_data(gender=message.text)
    await update_user_data(message.from_user.id, 'gender', state)
    await show_updated_profile(message, state)  # Показываем обновленный профиль
    await state.clear()  # Сбрасываем состояние после показа профиля

async def edit_age(message: types.Message, state: FSMContext):
    await state.update_data(age=int(message.text))
    await update_user_data(message.from_user.id, 'age', state)
    await show_updated_profile(message, state)  # Показываем обновленный профиль
    await state.clear()  # Сбрасываем состояние после показа профиля

async def edit_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await update_user_data(message.from_user.id, 'city', state)
    await show_updated_profile(message, state)  # Показываем обновленный профиль
    await state.clear()  # Сбрасываем состояние после показа профиля

async def edit_photos(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == 'пропустить':
        logger.info("Skip command received")
        await state.update_data(photos=[])
        await update_user_data(message.from_user.id, 'photos', state)
        await show_updated_profile(message, state)  # Показываем обновленный профиль
        await state.clear()  # Сбрасываем состояние после показа профиля
        return

    if message.photo:
        photo_id = message.photo[-1].file_id
        logger.info(f"Received photo ID: {photo_id}")

        data = await state.get_data()
        current_photos = set()
        current_photos.add(photo_id)
        await state.update_data(photos=list(current_photos))
        logger.info("Photos updated in state.")

        if 'timer_handle' in data:
            data['timer_handle'].cancel()
        timer_callback = partial(show_updated_profile, message=message, state=state)
        timer_handle = asyncio.get_event_loop().call_later(3, lambda: asyncio.create_task(timer_callback()))
        await state.update_data(timer_handle=timer_handle)

    logger.info("Handling complete.")

async def edit_games(message: types.Message, state: FSMContext):
    await state.update_data(favorite_games=message.text)
    await update_user_data(message.from_user.id, 'favorite_games', state)
    await show_updated_profile(message, state)  # Показываем обновленный профиль
    await state.clear()  # Сбрасываем состояние после показа профиля

async def edit_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await update_user_data(message.from_user.id, 'description', state)
    await show_updated_profile(message, state)  # Показываем обновленный профиль
    await state.clear()  # Сбрасываем состояние после показа профиля

async def show_updated_profile(message: types.Message, state: FSMContext):
    profile_data = await state.get_data()

    # Заполнить отсутствующие значения пустыми строками
    profile_data.setdefault('username', 'Не указано')
    profile_data.setdefault('gender', 'Не указано')
    profile_data.setdefault('age', 'Не указано')
    profile_data.setdefault('city', 'Не указано')
    profile_data.setdefault('photos', [])
    profile_data.setdefault('favorite_games', 'Не указано')
    profile_data.setdefault('description', 'Не указано')
    profile_data.setdefault('profile_link', 'Не указано')

    await send_profile_preview(message, profile_data)
    is_editing_from_menu = profile_data.get('editing_from_menu', False)
    
    if is_editing_from_menu:
        await message.answer("Изменения сохранены.", reply_markup=personal_account_keyboard(True))
    else:
        await message.answer("if все верно, нажмите 'Подтвердить'. if нужно что-то изменить, нажмите 'Изменить'.", reply_markup=confirm_profile_keyboard())

async def toggle_display_status(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_data = await get_user(user_id)
    if user_data:
        current_status = user_data[9]  # Позиция display_status в user_data
        new_status = "да" if current_status == "нет" else "нет"
        preferred_gender = user_data[10]  # Позиция preferred_gender в user_data
        preferred_gender = preferred_gender if preferred_gender else "нейтральный"
        await update_user(user_id, "display_status", new_status)
        # Заново получаем данные пользователя из базы данных после обновления
        user_data = await get_user(user_id)
        new_keyboard = personal_account_keyboard(new_status, preferred_gender)
        await update_reply_markup(call.message, new_keyboard)
        await call.answer("Статус обновлен.")
    else:
        await call.answer("Профиль не найден.")

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def keyboard_to_str(keyboard):
    return [[str(button) for button in row] for row in keyboard.inline_keyboard]

async def update_reply_markup(message, new_keyboard):
    current_reply_markup = keyboard_to_str(message.reply_markup)
    new_reply_markup = keyboard_to_str(new_keyboard)
    
    if new_reply_markup != current_reply_markup:
        await message.edit_reply_markup(reply_markup=new_keyboard)

async def toggle_preferred_gender(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_data = await get_user(user_id)
    if user_data:
        current_preferred_gender = user_data[10]  # Позиция preferred_gender в user_data
        current_preferred_gender = current_preferred_gender if current_preferred_gender else "нейтральный"

        new_preferred_gender = {
            "нейтральный": "женский",
            "женский": "мужской",
            "мужской": "нейтральный"
        }.get(current_preferred_gender, "нейтральный")
        
        if new_preferred_gender != current_preferred_gender:
            await update_user(user_id, "preferred_gender", new_preferred_gender)
            # Заново получаем данные пользователя из базы данных после обновления
            user_data = await get_user(user_id)
            new_keyboard = personal_account_keyboard(user_data[9], new_preferred_gender)
            await update_reply_markup(call.message, new_keyboard)
            await call.answer(f"Предпочтительный пол изменен на {new_preferred_gender.capitalize()}.")
        else:
            await call.answer("Пол не изменился.")
    else:
        await call.answer("Профиль не найден.")




async def cmd_lk(event: Union[types.Message, types.CallbackQuery], state: FSMContext, bot: Bot):
    if isinstance(event, types.CallbackQuery):
        message = event.message
        user_id = event.from_user.id
        await event.answer()  # Ответ на колбэк-запрос
        try:
            await message.delete()  # Удаление исходного сообщения с кнопкой
        except Exception:
            logger.error("Не удалось удалить сообщение")
    else:
        message = event
        user_id = message.from_user.id

    user_data = await get_user(user_id)
    if not user_data:
        await message.answer("Данные профиля не найдены.")
        return

    user_id, username, gender, age, city, photos, favorite_games, description, profile_link, display_status, preferred_gender, likes = user_data
    profile_data = {
        'username': username,
        'gender': gender,
        'age': age,
        'city': city,
        'photos': photos,
        'favorite_games': favorite_games,
        'description': description,
        'profile_link': profile_link,
        'display_status': display_status,
        'preferred_gender': preferred_gender,
        'likes': likes
    }
    await state.update_data(profile_data)

    profile_text = (
        f"Имя: {username}\n"
        f"Пол: {gender}\n"
        f"Возраст: {age}\n"
        f"Город: {city}\n"
        f"Любимые игры: {favorite_games}\n"
        f"Описание: {description}\n"
        f"Ссылка на профиль: {profile_link}\n"
    )

    # Отправка фотографий, if они есть
    if photos:
        media_group = [types.InputMediaPhoto(media=photo_id) for photo_id in photos]
        try:
            await bot.send_media_group(chat_id=message.chat.id, media=media_group)
        except Exception as e:
            logger.error(f"Ошибка при отправке фотографий: {str(e)}")
            await message.answer("Произошла ошибка при отправке фотографий.")
    
    # Отправка текста профиля с клавиатурой
    try:
        await message.answer(profile_text, reply_markup=personal_account_keyboard(display_status, preferred_gender))
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await message.answer("Произошла ошибка при отображении данных профиля.")

async def edit_account_from_menu(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("Что вы хотите изменить?", reply_markup=edit_profile_keyboard())
    await state.set_state(PersonalAccount.waiting_for_edit_choice)
    await state.update_data(editing_from_menu=True)  # Указываем, что редактирование идет из меню

async def confirm_profile_from_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()  # Сброс состояния после завершения редактирования
    await cmd_lk(call, state, call.bot)  # Возвращаемся в личный кабинет