from collections import defaultdict
from typing import List, Tuple, Dict, Any
import asyncio

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
from telegram_videogame_bot.prices_func import convert_to_rub

router = Router()

GAMES_PER_PAGE = 15

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

    regions_sel: set = data.get("regions", {"RU"})
    platforms: set = data.get("platforms", set())

    # --- Получение цен для найденных игр ---
    offer_tasks = []
    task_meta = []  # (store_name, region)

    for store_name, game_id in game_ids.items():
        for reg in regions_sel:
            # GOG отдаёт одну цену, нет смысла запрашивать другие регионы
            if store_name == "gog" and reg != "RU":
                continue
            if store_name == "steam":
                offer_tasks.append(steam_store.get_offers(game_id, reg))
            elif store_name == "epic":
                offer_tasks.append(epic_store.get_offers(game_id, reg))
            elif store_name == "gog":
                offer_tasks.append(gog_store.get_offers(game_id, reg))
            # elif store_name == "origin":
            #     offer_tasks.append(origin_store.get_offers(game_id, reg))
            elif store_name == "ms":
                offer_tasks.append(ms_store.get_offers(game_id, reg))
            elif store_name == "ps":
                offer_tasks.append(ps_store.get_offers(game_id, reg))
            task_meta.append((store_name, reg))

    # --- Обработка и отображение результатов ---
    price_results = await asyncio.gather(*offer_tasks, return_exceptions=True)

    async def fmt_price(p: float, cur: str) -> str:
        if cur == "FREE":
            return "<b>Бесплатно</b>"
        rub_price_str = ""
        if cur not in ["RUB", "Р", "₽"]:
            rub_price = await convert_to_rub(p, cur)
            if rub_price:
                rub_price_str = f" (<i>~{int(rub_price)} ₽</i>)"
        price_str = f"{p:g}" if cur in ["RUB", "Р", "₽"] else f"{p:.2f}"
        return f"<b>{price_str} {cur}</b>{rub_price_str}"

    # --- Группируем по магазину/региону ---
    store_region: dict[str, dict[str, tuple]] = defaultdict(dict)
    for (store, reg), result in zip(task_meta, price_results):
        if isinstance(result, Exception):
            logger.error(f"Ошибка получения цены {store} {reg}: {result}")
            continue
        if result:
            offer = result[0]
            store_region[store][reg] = offer

    if not store_region:
        await editable_message.edit_text(
            f"Не удалось найти актуальные цены для <b>{selected_title}</b>.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return

    # Дополняем магазины, чтобы отображались только релевантные
    selected_stores = set(store_region.keys())
    # Если у игры есть id в game_ids, но офферов нет (например, недоступен регион)—добавим пустую запись
    for _sn in game_ids.keys():
        store_region.setdefault(_sn, {})

    # Prefetch курсов валют, чтобы ускорить convert_to_rub
    from telegram_videogame_bot.prices_func import _fetch_rate_to_rub  # type: ignore

    # собираем все валюты, которые не RUB/FREE
    cur_set = set()
    for off_dict in store_region.values():
        for _reg, offer in off_dict.items():
            _sn, _price, cur, *_ = offer
            if cur not in ["RUB", "Р", "₽", "FREE"]:
                cur_set.add(cur)

    if cur_set:
        await asyncio.gather(*[_fetch_rate_to_rub(c) for c in cur_set])

    # --- Вычисляем среднюю цену (в рубляx) для сортировки магазинов ---
    async def avg_rub(offers_dict):
        rubs = []
        for reg, offer in offers_dict.items():
            _sn, price, cur, *_ = offer
            rub = price if cur in ["RUB", "Р", "₽"] else await convert_to_rub(price, cur)
            if rub is not None:
                rubs.append(rub)
        return sum(rubs) / len(rubs) if rubs else float("inf")

    store_avg = {store: await avg_rub(off_dict) for store, off_dict in store_region.items()}
    stores_sorted = sorted(store_region.keys(), key=lambda s: store_avg[s])

    # --- Форматируем вывод ---
    lines = []
    flag_map = {
        "RU": "🇷🇺", "TR": "🇹🇷", "AR": "🇦🇷", "BR": "🇧🇷", "US": "🇺🇸",
        "IN": "🇮🇳", "UA": "🇺🇦", "KZ": "🇰🇿", "PL": "🇵🇱",
    }

    for store in stores_sorted:
        off_dict = store_region[store]
        rub_pairs = []
        for reg in regions_sel:
            if reg in off_dict:
                _sn, price, cur, *_ = off_dict[reg]
                rub_val = price if cur in ["RUB", "Р", "₽"] else await convert_to_rub(price, cur)
                rub_pairs.append((reg, rub_val if rub_val is not None else float("inf")))
            else:
                rub_pairs.append((reg, float("inf")))

        region_sorted = [r for r, _ in sorted(rub_pairs, key=lambda x: x[1])]
        region_parts = []
        for reg in region_sorted:
            if reg in off_dict:
                _sn, price, cur, url, *rest = off_dict[reg]
                plus_flag = rest[0] if rest else False

                # --- подписочные варианты ---
                if plus_flag and store == "ms" and price <= 0.01:
                    price_str = "В подписке"
                elif price <= 0.01 and store == "ps" and plus_flag:
                    price_str = "PS Plus"
                else:
                    price_str = await fmt_price(price, cur)

                # --- подписка: Game Pass или PS Plus ---
                sub_suffix = ""
                if len(off_dict[reg]) >= 5:
                    if store == "ms" and off_dict[reg][4]:
                        # Если передана скидка в 7-м элементе — показываем обе цены
                        if len(off_dict[reg]) >= 7 and off_dict[reg][6]:
                            disc_val = off_dict[reg][6]
                            disc_str = await fmt_price(disc_val, cur)
                            price_str = f"{price_str} (С Game Pass {disc_str})"
                            sub_suffix = ""  # уже указали
                        else:
                            sub_suffix = " <i>(в Game Pass)</i>"
                    elif store == "ps" and off_dict[reg][4]:
                        # Если передана цена со скидкой – показываем обе
                        if len(off_dict[reg]) >= 8 and off_dict[reg][7]:
                            disc_val = off_dict[reg][7]
                            disc_str = await fmt_price(disc_val, cur)
                            price_str = f"{price_str} (PS Plus {disc_str})"
                            sub_suffix = ""
                        else:
                            sub_suffix = " <i>(PS Plus)</i>"

                # --- совместимость платформ ---
                hw_suffix = ""
                if store == "ms":
                    hardware = off_dict[reg][5] if len(off_dict[reg]) >= 6 else []
                    if "xbox_one" in platforms and "XboxOne" not in hardware and "XboxSeries" in hardware:
                        pass
                    if "xbox_one" in platforms and "XboxOne" not in hardware:
                        hw_suffix = " <i>(Series only)</i>"
                    elif "xbox_series" in platforms and not any(h.startswith("XboxSeries") for h in hardware):
                        hw_suffix = " <i>(One only)</i>"
                elif store == "ps":
                    hardware = off_dict[reg][5] if len(off_dict[reg]) >= 6 else []
                    if "ps4" in platforms and "PS4" not in hardware and "ps5" in platforms:
                        pass
                    if "ps4" in platforms and "PS4" not in hardware:
                        hw_suffix = " <i>(PS5 only)</i>"
                    elif "ps5" in platforms and "PS5" not in hardware:
                        hw_suffix = " <i>(PS4 only)</i>"

                # Избегаем дублирования пометки, когда игра уже «В подписке»
                if store == "ms" and price_str == "В подписке":
                    sub_suffix = ""

                # --- депозит для предзаказов в PlayStation Store ---
                deposit_suffix = ""
                if store == "ps" and len(off_dict[reg]) >= 7 and off_dict[reg][6]:
                    deposit_suffix = " <i>(депозит)</i>"

                region_parts.append(f"{flag_map.get(reg, reg)} <a href='{url}'>{price_str}{sub_suffix}{deposit_suffix}{hw_suffix}</a>")
            else:
                region_parts.append(f"{flag_map.get(reg, reg)} 🚫")
        display = STORE_DISPLAY.get(store, store.capitalize())
        regions_text = "\n   " + "\n   ".join(region_parts)
        lines.append(f"• <b>{display}</b>:" + regions_text)

    text = f"💰 Актуальные цены для <b>{selected_title}</b>:\n\n" + "\n".join(lines)
    await editable_message.edit_text(
        text, parse_mode="HTML", disable_web_page_preview=True,
        reply_markup=offers_keyboard(str(game_index))
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

    await message.answer("⏳ Ищу игры во всех магазинах...")

    # Дисклеймер о кириллице
    if any("\u0400" <= ch <= "\u04FF" for ch in message.text):
        await message.answer(
            "⚠️ Русские названия могут не находиться в некоторых магазинах (например, GOG). "
            "Попробуйте латинское написание, если нужная игра не найдена."
        )

    data = await state.get_data()
    platforms: set = data.get("platforms", set())
    regions_sel: set = data.get("regions", {"RU"})
    primary_region = next(iter(regions_sel))
    
    tasks: list = []
    store_names: list[str] = []

    pc_selected = "pc" in platforms
    xbox_selected = any(p in platforms for p in ("xbox_series", "xbox_one"))
    ps_selected = any(p in platforms for p in ("ps5", "ps4"))

    if pc_selected:
        tasks.append(steam_store.search_games(message.text))
        store_names.append("steam")

        tasks.append(epic_store.search_games(message.text, primary_region))
        store_names.append("epic")

        tasks.append(gog_store.search_games(message.text, primary_region))
        store_names.append("gog")

    # Xbox Store поддерживает PC и консоли
    if pc_selected or xbox_selected:
        tasks.append(ms_store.search_games(message.text, region=primary_region))
        store_names.append("ms")

    # PlayStation Store
    if ps_selected:
        tasks.append(ps_store.search_games(message.text, region=primary_region))
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
            for game_id, title in result:
                all_games.append((store_name, game_id, title))

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


def group_games_by_title(games: List[Tuple[str, str, str]]) -> List[Dict[str, Any]]:
    """Группирует товары по названию так, чтобы:
    • одна и та же игра из разных магазинов склеивалась,
    • но отдельные издания (DLC / Deluxe / Bundle / Nightreign …) оставались разными кнопками.
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

    for store, game_id, title in games:
        if not title:
            continue

        norm = normalize(title)
        tokens = set(norm.replace("-", " ").replace(":", " ").split())

        marker_tokens = frozenset(t for t in tokens if t in MARKERS)
        base_tokens = frozenset(t for t in tokens if t not in MARKERS)

        key = (base_tokens, marker_tokens)

        if key not in groups:
            groups[key] = {"title": title, "ids": {store: game_id}}
        else:
            # При конфликте названий выбираем более длинное (часто полное)
            if len(title) > len(groups[key]["title"]):
                groups[key]["title"] = title
            groups[key]["ids"].setdefault(store, game_id)

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