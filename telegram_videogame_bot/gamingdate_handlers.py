from aiogram import Dispatcher, types
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from gamingdate_keyboards import gamingdate_main_menu, search_navigation_keyboard, likes_keyboard, like_action_keyboard, back_to_likes_keyboard
from gamingdate_func import find_potential_friends, add_like, send_notification, get_likes, remove_like 
from base_keyboards import reply_menu_keyboard
from personalAccount_DB import get_user, update_user


async def cmd_gmdate(message: types.Message | types.CallbackQuery, reply_markup=None):
    user_data = await get_user(message.from_user.id)
    if not user_data:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Вернуться в меню", callback_data="main_menu")]
        ])
        if isinstance(message, types.Message):
            await message.answer("Вашего профиля нет в базе! Чтобы дальше пользоваться сервисом, нужно его создать! Для этого отправьте - /start", reply_markup=keyboard)
        elif isinstance(message, types.CallbackQuery):
            await message.message.edit_text("Вашего профиля нет в базе! Чтобы дальше пользоваться сервисом, нужно его создать! Для этого отправьте - /start", reply_markup=keyboard)
        return

    # Обновляем display_status на 'да'
    await update_user(message.from_user.id, 'display_status', 'да')

    welcome_text = (
        "Добро пожаловать в GamingDate! Здесь вы можете найти друзей для совместных игр, включая настольные игры. "
        "Посмотреть и отредактировать свой аккаунт можно в личном кабинете.\n\n"
        "При просмотре анкет ваш аккаунт автоматически будет отображаться в сервисе! "
        "Изменить это можно в личном кабинете."
    )

    try:
        if isinstance(message, types.Message):
            await message.answer(welcome_text, reply_markup=reply_markup or gamingdate_main_menu())
        elif isinstance(message, types.CallbackQuery):
            await message.message.edit_text(welcome_text, reply_markup=reply_markup or gamingdate_main_menu())
    except Exception as e:
        print(f"Ошибка при обработке колбэк-запроса: {e}")

async def start_search(call: CallbackQuery, state: FSMContext):
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Не удалось удалить сообщение: {e}")
        # Можно добавить логирование ошибки здесь
    
    user_data = await get_user(call.from_user.id)
    if user_data:
        viewed_users = set()  # Инициализация пустого множества просмотренных пользователей
        potential_friends = await find_potential_friends(user_data, viewed_users)
        if not potential_friends:
            await call.message.answer("К сожалению, не найдено подходящих пользователей.")
            return
        await state.update_data(potential_friends=potential_friends, current_index=0, viewed_users=viewed_users)
        await show_profile(call.message, potential_friends[0], state)
        
async def show_profile(message: Message, profile, state: FSMContext):
    profile_text = (
        f"Имя: {profile[1]}\n"
        f"Возраст: {profile[3]}\n"
        f"Гендер: {profile[2]}\n"
        f"Город: {profile[4]}\n"
        f"Игры: {profile[6]}\n"
        f"Описание: {profile[7]}\n"
    )
    # Отправка фотографий профиля
    if profile[5]:  # Если есть фотографии
        photos = profile[5].split(',')
        media = [types.InputMediaPhoto(media=photo) for photo in photos]
        await message.answer_media_group(media)
    
    await message.answer(profile_text, reply_markup=search_navigation_keyboard())
    data = await state.get_data()
    viewed_users = data.get('viewed_users', set())
    viewed_users.add(profile[0])  # Используем add вместо append
    await state.update_data(viewed_users=viewed_users)

async def handle_search_navigation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # Проверка наличия данных в состоянии
    if 'potential_friends' not in data or 'current_index' not in data:
        await message.answer("Не могу продолжить, так как данные отсутствуют. Пожалуйста, начните поиск заново.", reply_markup=reply_menu_keyboard)
        return

    potential_friends = data['potential_friends']
    current_index = data['current_index']
    viewed_users = data.get('viewed_users', set())

    if message.text == "⏭️":
        current_index += 1
        while current_index < len(potential_friends) and potential_friends[current_index][0] in viewed_users:
            current_index += 1
        if current_index < len(potential_friends):
            await state.update_data(current_index=current_index)
            await show_profile(message, potential_friends[current_index], state)
        else:
            # Обновляем список потенциальных друзей, если все пользователи просмотрены
            user_data = await get_user(message.from_user.id)
            viewed_users.clear()  # Обнуляем список просмотренных пользователей
            potential_friends = await find_potential_friends(user_data, viewed_users)
            if potential_friends:
                current_index = 0
                await state.update_data(potential_friends=potential_friends, current_index=current_index, viewed_users=viewed_users)
                await show_profile(message, potential_friends[current_index], state)
            else:
                await message.answer("Больше нет пользователей.")
    elif message.text == "👾":
        liked_user_id = potential_friends[current_index][0]
        await add_like(message.from_user.id, liked_user_id)
        await send_notification(message.bot, liked_user_id, "Вас Лайкнули! Бегом смотреть!")        
        await message.answer("Лайк отправлен!")
    elif message.text == "Хватит":
        # Отправляем сообщение с пожеланиями и меню
        await message.answer("Надеюсь, ты сегодня нашел себе нового друга. Возвращайся скорее за новым общением!", reply_markup=reply_menu_keyboard)
        # Используем функцию cmd_gmdate
        await cmd_gmdate(message)
        # Сброс состояния FSM
        await state.clear()

async def view_likes(call: CallbackQuery, state: FSMContext, page: int = 0):
    user_id = call.from_user.id
    likes = await get_likes(user_id)
    if not likes:
        await call.message.edit_text(
            "Никто еще не лайкнул ваш профиль. Попробуйте снова в GamingDate!",
            reply_markup=likes_keyboard([], 0, 0)
        )
        return

    # Пагинация
    likes_per_page = 6
    start_index = page * likes_per_page
    end_index = start_index + likes_per_page
    paginated_likes = likes[start_index:end_index]
    likes_data = [await get_user(int(like)) for like in paginated_likes]
    likes_text = "\n".join([f"{index + 1}. {like[1]}, {like[3]}, {like[2]}, {like[4]}, {like[6]}" for index, like in enumerate(likes_data, start=start_index)])

    await call.message.edit_text(
        f"Ваши лайки:\n{likes_text}",
        reply_markup=likes_keyboard(paginated_likes, page, len(likes))
    )

async def view_like(call: CallbackQuery, state: FSMContext):
    query_data = call.data.split("_")
    index = int(query_data[2]) - 1
    user_id = call.from_user.id
    likes = await get_likes(user_id)
    liked_user_id = int(likes[index])
    liked_user_data = await get_user(liked_user_id)
    
    profile_text = (
        f"Имя: {liked_user_data[1]}\n"
        f"Пол: {liked_user_data[2]}\n"
        f"Возраст: {liked_user_data[3]}\n"
        f"Город: {liked_user_data[4]}\n"
        f"Игры: {liked_user_data[6]}\n"
        f"Описание: {liked_user_data[7]}\n"
    )

    # Удаление предыдущего сообщения
    await call.message.delete()

    # Отправка фотографий профиля
    if liked_user_data[5]:  # Если есть фотографии
        photos = liked_user_data[5]
        media = [types.InputMediaPhoto(media=photo) for photo in photos]
        await call.message.answer_media_group(media)

    await call.message.answer(profile_text, reply_markup=like_action_keyboard())
    await state.update_data(current_like_index=index)

async def like_user(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    likes = await get_likes(user_id)
    current_index = data['current_like_index']
    liked_user_id = int(likes[current_index])

    # Удаление лайка из списка
    await remove_like(user_id, liked_user_id)
    liked_user_data = await get_user(liked_user_id)
    user_data = await get_user(user_id)

    # Отправка уведомления и ссылки
    await call.message.edit_text(f"Вы лайкнули {liked_user_data[1]}. Вот ссылка на его профиль: {liked_user_data[8]}", reply_markup=back_to_likes_keyboard())
    await send_notification(call.bot, liked_user_id, f"Ваш профиль лайкнул пользователь {user_data[1]}! Вот ссылка на его профиль: {user_data[8]}")

async def skip_user(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    likes = await get_likes(user_id)
    current_index = data['current_like_index']

    if current_index >= len(likes):
        await call.message.answer("Произошла ошибка: индекс выходит за пределы списка.")
        return

    liked_user_id = int(likes[current_index])

    # Удаление лайка из списка
    await remove_like(user_id, liked_user_id)

    # Обновление индекса и состояния
    likes = await get_likes(user_id)
    if current_index >= len(likes):
        current_index = max(0, len(likes) - 1)
    
    await state.update_data(current_like_index=current_index)

    # Вернуться к списку лайков
    await view_likes(call, state)

async def back_to_likes(call: CallbackQuery, state: FSMContext):
    await view_likes(call, state)

async def dismiss_notification(call: CallbackQuery):
    await call.message.delete()

def register_handlers_gamingdate(dp: Dispatcher):
    dp.callback_query.register(cmd_gmdate, lambda c: c.data == "call_gamingdate")
    dp.callback_query.register(start_search, lambda c: c.data == "start_search")
    dp.message.register(handle_search_navigation, lambda message: message.text in ["👾", "⏭️", "Хватит"])
    dp.callback_query.register(view_likes, lambda c: c.data == "view_gdates")
    dp.callback_query.register(view_like, lambda c: c.data.startswith("view_like_"))
    dp.callback_query.register(like_user, lambda c: c.data == "like_user")
    dp.callback_query.register(skip_user, lambda c: c.data == "skip_user")
    dp.callback_query.register(back_to_likes, lambda c: c.data == "back_to_likes")
    dp.callback_query.register(dismiss_notification, lambda c: c.data == "dismiss")
    dp.callback_query.register(lambda call, state: view_likes(call, state, int(call.data.split("_")[2])), lambda c: c.data.startswith("view_likes_"))