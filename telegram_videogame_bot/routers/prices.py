from collections import defaultdict
from typing import List, Tuple, Dict, Any
import asyncio
import re  # для безопасного удаления HTML-тегов
import aiohttp  # для PS Store fallback

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger
from fuzzywuzzy import fuzz, process

# Добавляем PlayStation Store
from telegram_videogame_bot import epic_store, gog_store, steam_store, ms_store, ps_store, utils
# from telegram_videogame_bot import origin_store
from telegram_videogame_bot.base_keyboards import inline_menu_keyboard
from telegram_videogame_bot.prices_keyboards import (
    build_games_keyboard,
    build_regions_keyboard,
    REGIONS,
    build_platform_keyboard,
    cancel_keyboard,
    offers_keyboard
)
from telegram_videogame_bot.prices_func import convert_currency

router = Router()

GAMES_PER_PAGE = 15

# Создаём словарь с флагами для регионов для красивого отображения
REGION_FLAGS = {code: name.split(" ")[0] for code, name in REGIONS}


class PriceStates(StatesGroup):
    waiting_for_platforms = State()
    waiting_for_region = State()
    waiting_for_query = State()
    waiting_for_game_choice = State()
    showing_prices = State()


# Символы валют (по ISO)
CURRENCY_SYMBOLS = {
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "BRL": "R$",
    "CAD": "C$",
    "AUD": "A$",
    "CNY": "¥",
}

# Человекочитаемые названия магазинов для отображения пользователю
STORE_DISPLAY = {
    "steam": "Steam",
    "epic": "Epic Games",
    "gog": "GOG",
    "ms": "Xbox Store",
    "ps": "PlayStation Store",
}


@router.message(Command("prices"))
async def cmd_prices(message: types.Message, state: FSMContext):
    if not await utils.check_subscription(message, message.bot):
        return
    await state.clear()
    await state.update_data(platforms=set())
    await message.answer(
        "Выберите платформы для поиска:",
        reply_markup=build_platform_keyboard(set()),
    )
    await state.set_state(PriceStates.waiting_for_platforms)


@router.callback_query(lambda c: c.data.startswith("plat_toggle:"), PriceStates.waiting_for_platforms)
async def toggle_platform(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    data = await state.get_data()
    selected: set = data.get("platforms", set())

    if code in selected:
        selected.remove(code)
    else:
        selected.add(code)

    await state.update_data(platforms=selected)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_platform_keyboard(selected)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.error(f"Error updating platform keyboard: {e}")
    await callback.answer()


@router.callback_query(F.data == "plat_ok", PriceStates.waiting_for_platforms)
async def confirm_platforms(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("platforms"):
        await callback.answer("⚠️ Пожалуйста, выберите хотя бы одну платформу.", show_alert=True)
        return

    await state.update_data(regions=set())
    await callback.message.edit_text(
        "Выберите регионы для поиска цен:", reply_markup=build_regions_keyboard(set())
    )
    await state.set_state(PriceStates.waiting_for_region)
    await callback.answer()


# --- Region selection (multi) ---

@router.callback_query(lambda c: c.data.startswith("region_toggle:"), PriceStates.waiting_for_region)
async def toggle_region(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    data = await state.get_data()
    selected: set = data.get("regions", set())

    if code in selected:
        selected.remove(code)
    else:
        selected.add(code)

    await state.update_data(regions=selected)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_regions_keyboard(selected)
        )
    except Exception as e:
        logger.error(f"Region keyboard update error: {e}")
    await callback.answer()


@router.callback_query(F.data == "region_select_all", PriceStates.waiting_for_region)
async def select_all_regions(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: set = data.get("regions", set())
    if selected and len(selected) == len(REGIONS):
        selected.clear()
    else:
        selected.update({code for code, _ in REGIONS})

    await state.update_data(regions=selected)
    await callback.message.edit_reply_markup(
        reply_markup=build_regions_keyboard(selected)
    )
    await callback.answer()


@router.callback_query(F.data == "region_ok", PriceStates.waiting_for_region)
async def confirm_regions(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("regions"):
        await callback.answer("⚠️ Выберите хотя бы один регион.", show_alert=True)
        return

    await callback.message.edit_text(
        "Теперь введите название игры:", reply_markup=cancel_keyboard()
    )
    await state.set_state(PriceStates.waiting_for_query)
    await callback.answer()


async def get_ps_regional_price(concept_id: str, region: str) -> tuple[str, dict | None]:
    """
    Получает цену для PS Store в определенном регионе, используя conceptId.
    Возвращает кортеж (использованный_id, данные_о_цене).
    """
    regional_product_id = await ps_store.get_product_id_from_concept(concept_id, region)
    
    if not regional_product_id:
        logger.warning(f"Не удалось найти regional_product_id для concept_id {concept_id} в регионе {region}")
        return f"concept:{concept_id}", None

    price_data = await ps_store.get_product_price(regional_product_id, region)
    return regional_product_id, price_data


async def show_prices_for_game(
    editable_message: types.Message, state: FSMContext, game_group: Dict[str, Any], game_index: int
):
    """
    Отображает цены для выбранной группы игр.
    `editable_message` используется для отправки/редактирования сообщений.
    """
    await editable_message.edit_text("⏳ Собираю цены (5–15 сек)...")

    data = await state.get_data()
    selected_title = game_group["title"]
    game_ids = game_group["ids"]
    ps_concept_id = game_group.get("ps_concept_id")

    regions_sel: set = data.get("regions", {"RU"})
    
    # --- Получение цен для найденных игр ---
    offer_tasks = []
    task_meta = []  # (store_name, region)

    ps_fallback_prices: Dict[str, dict] | None = None  # Цены из новой логики (без conceptId)

    # Определяем, какие регионы реально запрашивать для PS
    ps_regions_to_fetch = set(regions_sel)
    remap_ru_kz = "RU" in ps_regions_to_fetch or "KZ" in ps_regions_to_fetch
    if remap_ru_kz:
        ps_regions_to_fetch.discard("RU")
        ps_regions_to_fetch.discard("KZ")
        ps_regions_to_fetch.add("US")  # Убедимся, что US будет запрошен

    for store_name, game_id in game_ids.items():
        if store_name == "ps":
            if not ps_concept_id:
                # --- Новый fallback: используем product_id и invariant_name ---
                base_product_id = game_id
                if base_product_id.startswith("ps:"):
                    base_product_id = base_product_id[3:]

                invariant_name = game_group.get("ps_invariant_name")
                game_details = {
                    "name": selected_title,
                    "ps_store_id": base_product_id,
                    "invariant_name": invariant_name,
                }

                ps_region_codes = [c.lower() for c in ps_regions_to_fetch]

                # Запускаем в отдельной задаче с собственным ClientSession, чтобы не блокировать другие
                async def _get_fallback_prices():
                    async with aiohttp.ClientSession() as session:
                        return await ps_store.get_ps_store_prices(session, game_details, ps_region_codes)

                offer_tasks.append(_get_fallback_prices())
                task_meta.append(("ps_fallback", "ALL"))
                continue
            # --- Старый путь через conceptId ---
            for reg in ps_regions_to_fetch:
                offer_tasks.append(get_ps_regional_price(ps_concept_id, reg))
                task_meta.append((store_name, reg))
        else:
            # Для остальных магазинов логика прежняя
            for reg in regions_sel:
                if store_name == "gog" and reg != "RU":
                    continue
                
                module_map = {
                    "steam": steam_store, "epic": epic_store, 
                    "gog": gog_store, "ms": ms_store
                }
                if store_name in module_map:
                    offer_tasks.append(module_map[store_name].get_offers(game_id, reg))
                    task_meta.append((store_name, reg))

    # --- Обработка и отображение результатов ---
    price_results = await asyncio.gather(*offer_tasks, return_exceptions=True)

    # --- Группируем по магазину/региону ---
    store_region: dict[str, dict[str, list | dict]] = defaultdict(dict)
    ps_regional_ids = {}  # Для хранения региональных ID PS игр
    for (store, reg), result in zip(task_meta, price_results):
        if isinstance(result, Exception):
            logger.error(f"Ошибка получения цены {store} {reg}: {result}")
            continue
        if result:
            if store == "ps_fallback":
                # result – это dict region→price_info
                ps_fallback_prices = result  # сохраним для дальнейшей обработки
                for reg_code, price_info in result.items():
                    up_reg = reg_code.upper()
                    store_region["ps"][up_reg] = price_info
                    # Извлекаем product_id из URL
                    prod_id = price_info.get("url", "").split("/")[-1]
                    if prod_id:
                        ps_regional_ids[up_reg] = f"ps:{prod_id}"
            elif store == "ps":
                regional_id, price_data = result
                if price_data:
                    store_region[store][reg] = price_data
                    ps_regional_ids[reg] = regional_id
            else:
                store_region[store][reg] = result

    # Для PS Store копируем данные из US в RU/KZ, если требуется
    if remap_ru_kz and "ps" in store_region and "US" in store_region["ps"]:
        us_offers = store_region["ps"].get("US")
        us_id = ps_regional_ids.get("US")
        if us_offers:
            if "RU" in regions_sel:
                store_region["ps"]["RU"] = us_offers
                if us_id: ps_regional_ids["RU"] = us_id
            if "KZ" in regions_sel:
                store_region["ps"]["KZ"] = us_offers
                if us_id: ps_regional_ids["KZ"] = us_id

    if not any(store_region.values()):
        await editable_message.edit_text(
            f"Не удалось найти актуальные цены для <b>{selected_title}</b>.",
            parse_mode="HTML",
            reply_markup=offers_keyboard(game_index),
        )
        return

    # Дополняем магазины, чтобы отображались только релевантные
    for _sn in game_ids.keys():
        store_region.setdefault(_sn, {})

    async def fmt_price(p: float, cur: str) -> str:
        """Универсальный форматер цен с конвертацией в рубли."""
        if cur is None or p is None: return ""
        if cur == "FREE" or p == 0.0: return "<b>Бесплатно</b>"
        if cur in ["RUB", "Р", "₽", "INR", "JPY", "KRW", "HUF", "CLP", "VND"]:
            price_str = f"{int(round(p))}"
        else:
            price_str = f"{p:.2f}"
        main_price_formatted = f"<b>{price_str} {CURRENCY_SYMBOLS.get(cur, cur)}</b>"
        conv_price_str = ""
        if cur.upper() != 'RUB':
            converted = await convert_currency(p, cur, 'RUB')
            if converted:
                conv_price_str = f" (<i>~{int(converted)} ₽</i>)"
        return main_price_formatted + conv_price_str

    async def get_sort_price(store_name: str, offer_data: dict | list) -> float:
        """Рассчитывает цену для сортировки (в рублях)."""
        if not offer_data: return float('inf')
        
        final_price, currency, is_catalog = float('inf'), None, False

        if store_name == 'ps' and isinstance(offer_data, dict):
            final_price = offer_data.get("price", float('inf'))
            currency = offer_data.get("currency")
            is_catalog = offer_data.get("included_in_ps_plus", False)
        elif isinstance(offer_data, list):
            try:
                offer = offer_data[0]
                price = offer[1]
                currency = offer[2]
                
                # Безопасно получаем доп. поля
                is_catalog = offer[7] if len(offer) > 7 else False
                discount_val = offer[8] if len(offer) > 8 else None
                
                final_price = discount_val if discount_val is not None and discount_val < price else price
            except (ValueError, IndexError):
                return float('inf')

        if is_catalog and final_price == 0.0: return 0.0
        if currency is None or final_price is None or final_price == float('inf'): return float('inf')
        if currency.upper() in ["RUB", "Р", "₽", "FREE"]: return final_price if currency != "FREE" else 0.0
        rub_price = await convert_currency(final_price, currency, "RUB")
        return rub_price if rub_price is not None else float('inf')
    
    # --- Рендер сообщения ---
    async def _render_store_prices(store_name: str, offers_by_region: dict) -> str:
        lines = [f"<b>{STORE_DISPLAY.get(store_name, store_name.title())}:</b>"]
        if not offers_by_region:
            lines.append("  <i>Нет предложений</i>")
            return "\n".join(lines)

        sorting_prices = {reg: await get_sort_price(store_name, o) for reg, o in offers_by_region.items()}
        sorted_regions = sorted(offers_by_region.items(), key=lambda item: sorting_prices.get(item[0], float('inf')))

        for reg, offers in sorted_regions:
            if not offers: continue
            
            flag = REGION_FLAGS.get(reg, "❔")
            price_line_parts = [f"  {flag} <b>{reg}:</b>"]
            url = ""

            if store_name == 'ps':
                price_info = offers
                
                # Используем региональный ID, если он есть
                product_id = ps_regional_ids.get(reg, game_ids.get("ps", ""))
                if product_id.startswith("ps:"):
                    product_id = product_id[3:]
                    
                url = f"https://store.playstation.com/{ps_store._REGION_TO_LOCALE.get(reg, 'en-us')}/product/{product_id}"
                
                price, currency = price_info['price'], price_info['currency']
                old_price, ps_plus_price = price_info.get('old_price'), price_info.get('ps_plus_price')
                is_included = price_info.get('included_in_ps_plus')

                price_fmt = await fmt_price(price, currency)
                
                if is_included:
                    price_line_parts.append(f'<a href="{url}">Бесплатно в PS Plus</a>')
                    if price > 0: price_line_parts.append(f'(или {price_fmt})')
                elif old_price and old_price > price:
                    old_price_fmt = f"<s>{old_price:g} {CURRENCY_SYMBOLS.get(currency, currency)}</s>"
                    price_line_parts.append(f'<a href="{url}">{old_price_fmt} {price_fmt}</a>')
                elif ps_plus_price and ps_plus_price < price:
                     ps_plus_price_fmt = await fmt_price(ps_plus_price, currency)
                     price_line_parts.append(f'<a href="{url}">{price_fmt}</a> (PS+: {ps_plus_price_fmt})')
                else:
                    price_line_parts.append(f'<a href="{url}">{price_fmt}</a>')
            else: # Другие магазины
                try:
                    offer = offers[0]
                    label, price, currency, url = offer[0], offer[1], offer[2], offer[3]
                    discount_val = offer[4] if len(offer) > 4 and offer[4] is not None else None
                    is_plus = False # Для PC нерелевантно в данном контексте
                    deposit_flag = False # Аналогично
                except (ValueError, IndexError):
                    logger.warning(f"Не удалось распаковать оффер для {store_name}: {offers[0]}")
                    continue
                
                if currency == "FREE": price_line_parts.append(f'<a href="{url}">Бесплатно</a>')
                elif deposit_flag: price_line_parts.append(f'<a href="{url}">Предзаказ</a> ({await fmt_price(price, currency)})')
                elif discount_val is not None and discount_val < price:
                    old_price_fmt = f"<s>{price:g} {currency}</s>"
                    new_price_fmt = await fmt_price(discount_val, currency)
                    price_line_parts.append(f'<a href="{url}">{old_price_fmt} {new_price_fmt}</a>')
                else: price_line_parts.append(f'<a href="{url}">{await fmt_price(price, currency)}</a>')
            
            lines.append(" ".join(price_line_parts))
        return "\n".join(lines)

    # --- Сортировка магазинов по средней цене ---
    store_avg_prices = {}
    for store_name, offers_by_region in store_region.items():
        region_prices = [await get_sort_price(store_name, o) for o in offers_by_region.values() if o]
        valid_prices = [p for p in region_prices if p != float('inf')]
        store_avg_prices[store_name] = sum(valid_prices) / len(valid_prices) if valid_prices else float('inf')
    
    # --- Финальное сообщение ---
    price_details = []
    sorted_stores = sorted(store_region.items(), key=lambda item: store_avg_prices.get(item[0], float('inf')))

    for store, offers_by_reg in sorted_stores:
        price_details.append(await _render_store_prices(store, offers_by_reg))

    msg_text = f"✅ <b>{selected_title}</b>\n\n" + "\n\n".join(price_details)
    msg_text = re.sub(r'\n{3,}', '\n\n', msg_text).strip()
    
    await editable_message.edit_text(
        msg_text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=offers_keyboard(game_index),
    )
    await state.set_state(PriceStates.showing_prices)
    return


@router.message(PriceStates.waiting_for_query)
async def process_search_name(message: types.Message, state: FSMContext):
    """
    Первичный поиск по всем магазинам.
    Формирует единый список уникальных игр для выбора пользователем.
    """
    if not message.text:
        await message.answer("Пожалуйста, введите название для поиска.")
        return

    # Сохраняем исходный запрос для будущего использования в PS Store
    await state.update_data(user_query=message.text)
    
    await message.answer("⏳ Ищу игры во всех магазинах...")

    # Дисклеймер о кириллице
    if any("\u0400" <= ch <= "\u04FF" for ch in message.text):
        await message.answer(
            "⚠️ Русские названия могут не находиться в некоторых магазинах (например, GOG). "
            "Попробуйте латинское написание, если нужная игра не найдена."
        )

    data = await state.get_data()
    platforms: set = data.get("platforms", set())
    
    # Всегда используем 'US' как основной регион для поиска, чтобы получать английские названия
    primary_region_for_search = "US"
    
    tasks: list = []
    store_names: list[str] = []

    pc_selected = "pc" in platforms
    xbox_selected = any(p in platforms for p in ("xbox_series", "xbox_one"))
    ps_selected = any(p in platforms for p in ("ps5", "ps4"))

    if pc_selected:
        tasks.append(steam_store.search_games(message.text))
        store_names.append("steam")

        tasks.append(epic_store.search_games(message.text, primary_region_for_search))
        store_names.append("epic")

        tasks.append(gog_store.search_games(message.text, primary_region_for_search))
        store_names.append("gog")

    # Xbox Store поддерживает PC и консоли
    if pc_selected or xbox_selected:
        tasks.append(ms_store.search_games(message.text, region=primary_region_for_search))
        store_names.append("ms")

    # PlayStation Store
    if ps_selected:
        tasks.append(ps_store.search_games(message.text, region=primary_region_for_search))
        store_names.append("ps")

    if not tasks:
        await message.answer(
            "😔 Пока нет поддерживаемых магазинов для выбранных платформ.",
            reply_markup=inline_menu_keyboard,
        )
        return
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_games = []

    for store_name, result in zip(store_names, results):
        if isinstance(result, Exception):
            logger.error(f"Поиск в {store_name} завершился ошибкой: {result}")
        else:
            display_name = STORE_DISPLAY.get(store_name, store_name.capitalize())
            logger.info(f"Найдено {len(result)} игр в {display_name} по запросу '{message.text}'.")
            # Теперь search_games возвращает (game_id, title, concept_id, invariant_name)
            for item in result:
                if len(item) == 4: # PS Store
                    game_id, title, concept_id, invariant_name = item
                    all_games.append((store_name, game_id, title, concept_id, invariant_name))
                else: # Другие магазины
                    game_id, title = item
                    all_games.append((store_name, game_id, title, None, None))

    if not all_games:
        await message.answer(
            "😔 К сожалению, я ничего не нашёл. Попробуйте другое название.",
            reply_markup=cancel_keyboard(),
        )
        return

    # Группировка
    game_groups = group_games_by_title(all_games)

    # --- Сортировка по релевантности запроса ---
    query_norm = message.text.lower().strip()

    def _relevance_key(group):
        title_norm = group["title"].lower()
        if title_norm == query_norm:
            return (0, len(title_norm))
        if title_norm.startswith(query_norm):
            return (1, len(title_norm))
        if query_norm in title_norm:
            return (2, len(title_norm))
        return (3, len(title_norm))

    game_groups.sort(key=_relevance_key)
    
    # Сохраняем все группы и названия в состояние
    final_titles = [group["title"] for group in game_groups]
    await state.update_data(game_groups=game_groups, final_titles=final_titles)

    # Выводим список даже если группа одна — пользователь сам выберет нужный товар

    # Если игр для выбора не нашлось
    if not game_groups:
        await message.answer(
            "❌ По вашему запросу ничего не найдено.\n"
            "Попробуйте изменить запрос или выберите другие регионы/платформы."
        )
        return

    # Ограничение в 20 для одной страницы, в будущем можно добавить пагинацию
    await message.answer(
        "⬇️ Найдено несколько игр. Выберите нужную:",
        reply_markup=build_games_keyboard(game_groups),
    )
    await state.set_state(PriceStates.waiting_for_game_choice)


@router.callback_query(lambda c: c.data.startswith("price_game_"), PriceStates.waiting_for_game_choice)
async def process_game_choice(callback: types.CallbackQuery, state: FSMContext):
    """
    Получает выбранную группу игр и показывает для неё цены.
    """
    title_idx = int(callback.data.rsplit("_", 1)[1])
    data = await state.get_data()
    
    try:
        game_groups = data["game_groups"]
        selected_group = game_groups[title_idx]

        # Переходим к показу цен
        await show_prices_for_game(callback.message, state, selected_group, title_idx)
    except (KeyError, IndexError):
        await callback.message.edit_text("Произошла ошибка, попробуйте заново. /prices")
        return


@router.callback_query(F.data == "price_back")
async def price_back(callback: types.CallbackQuery, state: FSMContext):
    cur_state = await state.get_state()

    # С экрана с ценами -> назад к выбору игры
    if cur_state == PriceStates.showing_prices.state:
        data = await state.get_data()
        game_groups = data.get("game_groups", [])
        await callback.message.edit_text(
            "⬇️ Найдено несколько игр. Выберите нужную:",
            reply_markup=build_games_keyboard(game_groups),
        )
        await state.set_state(PriceStates.waiting_for_game_choice)

    # С экрана выбора игры -> назад к вводу названия
    elif cur_state == PriceStates.waiting_for_game_choice.state:
        await callback.message.edit_text(
            "Теперь введите название игры:", reply_markup=cancel_keyboard()
        )
        await state.set_state(PriceStates.waiting_for_query)

    # From query input -> back to region choice
    elif cur_state == PriceStates.waiting_for_query.state:
        data = await state.get_data()
        regions_sel: set = data.get("regions", set())
        await callback.message.edit_text(
            "Выберите регионы для поиска цен:", reply_markup=build_regions_keyboard(regions_sel)
        )
        await state.set_state(PriceStates.waiting_for_region)

    # From region choice -> back to platform choice
    elif cur_state == PriceStates.waiting_for_region.state:
        data = await state.get_data()
        selected: set = data.get("platforms", set())
        await callback.message.edit_text(
            "Выберите платформы для поиска:",
            reply_markup=build_platform_keyboard(selected),
        )
        await state.set_state(PriceStates.waiting_for_platforms)
    
    # From platform choice -> cancel and go to main menu
    else:
        await state.clear()
        await callback.message.edit_text("Действие отменено. Возврат в главное меню.")
        # Optionally, show the main menu again
        # await base_handlers.cmd_main_menu(callback.message, state)

        await callback.answer()


@router.callback_query(F.data == "price_cancel", StateFilter("*"))
async def price_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    # Можно вернуть в главное меню, если нужно
    # await base_handlers.cmd_main_menu(callback.message, state)
    await callback.answer()


def group_games_by_title(games: List[Tuple[str, str, str, str | None, str | None]]) -> List[Dict[str, Any]]:
    """Группирует товары по названию так, чтобы:
    • одна и та же игра из разных магазинов склеивалась,
    • но отдельные издания (DLC / Deluxe / Bundle / ...) оставались разными кнопками.
    Также сохраняет ps_invariant_name и ps_concept_id для группы.
    """
    if not games:
        return []

    MARKERS = {
        "dlc", "expansion", "bundle", "deluxe", "premium", "ultimate", "gold", "complete",
        "ost", "soundtrack", "edition", "collection", "season", "pass", "remaster", "remastered",
        "definitive", "vr", "dx", "redux"
    }

    def normalize(s: str) -> str:
        return (
            s.lower()
            .replace("®", "")
            .replace("™", "")
            .replace("©", "")
        )

    groups: Dict[Tuple[frozenset, frozenset], Dict[str, Any]] = {}

    for store, game_id, title, concept_id, invariant_name in games:
        if not title:
            continue

        norm = normalize(title)
        tokens = set(norm.replace("-", " ").replace(":", " ").split())

        marker_tokens = frozenset(t for t in tokens if t in MARKERS)
        base_tokens = frozenset(t for t in tokens if t not in MARKERS)

        key = (base_tokens, marker_tokens)

        if key not in groups:
            groups[key] = {"title": title, "ids": {store: game_id}}
            if store == "ps":
                if invariant_name:
                    groups[key]["ps_invariant_name"] = invariant_name
                if concept_id:
                    groups[key]["ps_concept_id"] = concept_id
        else:
            # При конфликте названий выбираем более длинное (часто полное)
            if len(title) > len(groups[key]["title"]):
                groups[key]["title"] = title
            groups[key]["ids"].setdefault(store, game_id)
            # Добавляем инварианты, если их еще нет
            if store == "ps":
                if invariant_name and "ps_invariant_name" not in groups[key]:
                    groups[key]["ps_invariant_name"] = invariant_name
                if concept_id and "ps_concept_id" not in groups[key]:
                    groups[key]["ps_concept_id"] = concept_id

    # Приводим к списку
    return sorted(groups.values(), key=lambda x: x["title"].lower()) 

# --- Pagination ---

@router.callback_query(lambda c: c.data.startswith("price_page_"), PriceStates.waiting_for_game_choice)
async def process_page_switch(callback: types.CallbackQuery, state: FSMContext):
    """Переключение страниц списка игр."""
    try:
        page = int(callback.data.split("_", 2)[2])
    except (IndexError, ValueError):
        await callback.answer()
        return

    data = await state.get_data()
    game_groups = data.get("game_groups", [])
    if not game_groups:
        await callback.answer()
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=build_games_keyboard(game_groups, page))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.error(f"Pagination edit error: {e}")
    await callback.answer() 


# --- Выбор издания PS --- 