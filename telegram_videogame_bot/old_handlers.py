async def cmd_sales(message: types.Message, state: FSMContext):
    await message.answer("Пожалуйста, введите часть названия игры для поиска:")
    await state.set_state(SearchQuery.waiting_for_query)  # Исправлено

async def process_search_query(message: types.Message, state: FSMContext):
    query = message.text
    await state.update_data(query=query)
    
    page = 1
    page_size = 10
    games_on_sale = await stores.get_steam_games_on_sale(query, page, page_size)
    
    if games_on_sale:
        response = f"Игры, соответствующие запросу '{query}' и участвующие в распродаже:\n\n"
        for game in games_on_sale:
            response += f"- {game['name']} ({game['price']}) - {game['url']}\n"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Следующая страница", callback_data=f"sales:{query}:{page+1}:{page_size}")]
        ])
        
        await message.answer(response, reply_markup=keyboard)
    else:
        await message.answer(f"Сейчас нет игр, соответствующих запросу '{query}' и участвующих в распродаже.")
        await message.answer("Пожалуйста, введите часть названия игры для поиска:")
        await state.set_state(SearchQuery.waiting_for_query)

async def process_search_sales(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.answer("Пожалуйста, введите часть названия игры для поиска:")
    await state.set_state(SearchQuery.waiting_for_query)  # Исправлено

async def process_show_commands(callback_query: types.CallbackQuery):
    await callback_query.answer()
    help_text = "Доступные команды:\n" \
                "/start - Начать работу с ботом\n" \
                "/stores - Поиск игр в магазинах\n" \
                "/help - Показать список команд"
    await callback_query.message.answer(help_text)    

async def callback_sales(callback_query: types.CallbackQuery):
    query, page, page_size = callback_query.data.split(':')[1:]
    page = int(page)
    page_size = int(page_size)
    games_on_sale = await stores.get_steam_games_on_sale(query, page, page_size)
    
    if games_on_sale:
        response = f"Игры, соответствующие запросу '{query}' и участвующие в распродаже:\n\n"
        for game in games_on_sale:
            response += f"- {game['name']} ({game['price']}) - {game['url']}\n"
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        
        if page > 1:
            prev_callback_data = f"sales:{query}:{page-1}:{page_size}"
            keyboard.inline_keyboard.append([types.InlineKeyboardButton(text="Предыдущая страница", callback_data=prev_callback_data)])
        
        next_callback_data = f"sales:{query}:{page+1}:{page_size}"
        keyboard.inline_keyboard.append([types.InlineKeyboardButton(text="Следующая страница", callback_data=next_callback_data)])
        
        await callback_query.message.edit_text(response, reply_markup=keyboard)
    else:
        await callback_query.answer("Больше нет игр, соответствующих запросу.")


async def cmd_store(message: types.Message, state: FSMContext):
    keyboard = create_store_choice_keyboard()
    await message.answer("Выберите магазин для поиска игр:", reply_markup=keyboard)
    await state.set_state(StoreChoice.choosing_store)  # Исправлено


async def process_search_option(callback_query: types.CallbackQuery, state: FSMContext):
    # Получение выбранного магазина из callback_data
    store = callback_query.data.split(':')[1]
    await state.update_data(store=store)

    # Создание клавиатуры с опциями поиска
    keyboard = create_search_options_keyboard()

    # Отправка сообщения с клавиатурой опций поиска
    await callback_query.message.edit_text("По каким играм осуществить поиск?", reply_markup=keyboard)

    # Переход в состояние выбора опции поиска
    await state.set_state(StoreChoice.choosing_search_option)


async def request_search_query(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer("Введите ключевое слово для поиска:")
    await state.set_state(StoreChoice.entering_query)


async def process_search_type(callback_query: types.CallbackQuery, state: FSMContext):
    search_type = callback_query.data.split(':')[1]
    await state.update_data(search_type=search_type)

    keyboard = create_filter_keyboard()
    await callback_query.message.edit_text("Выберите фильтры для поиска:", reply_markup=keyboard)
    await state.set_state(StoreChoice.choosing_filters)  # Исправлено

async def process_filter(callback_query: types.CallbackQuery, state: FSMContext):
    filter_type = callback_query.data.split(':')[1]
    current_data = await state.get_data()
    filters = current_data.get("filters", [])

    # Проверяем, если фильтр уже выбран, убираем его, иначе добавляем
    if filter_type in filters:
        filters.remove(filter_type)
        await callback_query.answer(f"Фильтр '{filter_type}' удален.")
    else:
        filters.append(filter_type)
        await callback_query.answer(f"Фильтр '{filter_type}' добавлен.")

    await state.update_data(filters=filters)

    # Обновляем клавиатуру с учетом выбранных фильтров
    keyboard = create_filter_keyboard(filters)

    # Обновляем сообщение с новой клавиатурой
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)


async def process_search(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    store = user_data.get('store', 'steam')
    search_type = user_data.get('search_type', 'all')
    filters = user_data.get('filters', [])

    parts = callback_query.data.split(':')
    if len(parts) > 1 and parts[0] == 'search':
        try:
            page = int(parts[1])
        except ValueError:
            page = 1  # Если происходит ошибка при преобразовании, устанавливаем страницу 1
    else:
        page = 1  # Устанавливаем страницу 1, если формат данных не соответствует ожидаемому

    games = await stores.parse_steam(query="", sales_only=(search_type == 'sales'), filters=filters, page=page, page_size=10)

    games_text = '\n'.join(f"{game['name']} - {game['price']} - {game['rating']} - [Link]({game['link']})" for game in games)

    # Создание и отправка клавиатуры с кнопками для навигации
    keyboard = types.InlineKeyboardMarkup()
    if page > 1:
        keyboard.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"search:{page-1}"))
    if len(games) == 10:  # Предполагаем, что это максимальное количество игр на странице
        keyboard.add(types.InlineKeyboardButton("Вперёд ➡️", callback_data=f"search:{page+1}"))
   
    await callback_query.message.edit_text(f"Найденные игры (Страница {page}):\n{games_text}", reply_markup=keyboard, parse_mode='Markdown')
    await callback_query.answer()