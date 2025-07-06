from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest

import utils
from steam_store import search_games as steam_search, get_offers as steam_offers

from prices_func import convert_to_rub
from prices_keyboards import games_keyboard, offers_keyboard, cancel_keyboard, platforms_keyboard, regions_keyboard
import base_handlers
import asyncio

router = Router()


class PriceStates(StatesGroup):
    waiting_for_platforms = State()
    waiting_for_region = State()
    waiting_for_query = State()
    waiting_for_game_choice = State()


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


@router.message(Command("prices"))
async def cmd_prices(message: types.Message, state: FSMContext):
    if not await utils.check_subscription(message, message.bot):
        return
    await state.update_data(platforms=set())
    await message.answer("Выберите предпочитаемые платформы:", reply_markup=platforms_keyboard(set()))
    await state.set_state(PriceStates.waiting_for_platforms)


@router.callback_query(lambda c: c.data.startswith("plat_toggle:"), PriceStates.waiting_for_platforms)
async def toggle_platform(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    data = await state.get_data()
    selected: set = set(data.get("platforms", set()))
    if code in selected:
        selected.remove(code)
    else:
        selected.add(code)
    await state.update_data(platforms=selected)
    await callback.message.edit_reply_markup(reply_markup=platforms_keyboard(selected))
    await callback.answer()


@router.callback_query(F.data == "plat_ok", PriceStates.waiting_for_platforms)
async def confirm_platforms(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("platforms"):
        await callback.answer("Выберите хотя бы одну платформу", show_alert=True)
        return
    await callback.message.edit_text("Выберите регион ценообразования:", reply_markup=regions_keyboard())
    await state.set_state(PriceStates.waiting_for_region)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("region:"), PriceStates.waiting_for_region)
async def choose_region(callback: types.CallbackQuery, state: FSMContext):
    region = callback.data.split(":")[1]
    await state.update_data(region=region)
    await callback.message.edit_text("Введите название игры:", reply_markup=cancel_keyboard())
    await state.set_state(PriceStates.waiting_for_query)
    await callback.answer()


@router.message(PriceStates.waiting_for_query)
async def process_search_name(message: types.Message, state: FSMContext):
    games = []
    data = await state.get_data()
    platforms: set = data.get("platforms", set())

    # Steam (ПК)
    if "pc" in platforms:
        games.extend(await steam_search(message.text))

    if not games:
        await message.answer("❌ Ничего не найдено. Попробуйте ещё раз.")
        return
    await message.answer("Выберите игру:", reply_markup=games_keyboard(games))
    await state.update_data(games=dict(games))
    await state.set_state(PriceStates.waiting_for_game_choice)


@router.callback_query(lambda c: c.data.startswith("price_game:"), PriceStates.waiting_for_game_choice)
async def process_game_choice(callback: types.CallbackQuery, state: FSMContext):
    game_id = callback.data.split(":", 1)[1]
    data = await state.get_data()
    game_name = data["games"].get(game_id)
    # Определяем источник по префиксу
    if game_id.startswith("steam:"):
        region_sel = data.get("region", "RU")
        offers = await steam_offers(game_id, region_sel)
    else:
        offers = []
    if not offers:
        await callback.message.answer("❌ Не удалось получить цены. Попробуйте позже.")
        return
    async def fmt_price(p: float, cur: str) -> str:
        # Показываем ₽ и исходную валюту, если она не RUB
        if cur == "RUB":
            return f"{p:g} ₽"
        rub = await convert_to_rub(p, cur)
        symbol = CURRENCY_SYMBOLS.get(cur, cur)
        if rub:
            return f"{rub:g} ₽  ({p:g} {symbol})"
        return f"{p:g} {symbol}"

    async def to_rub(p: float, cur: str):
        return p if cur == "RUB" else (await convert_to_rub(p, cur) or 1e9)

    # получаем текущий event loop для асинхронной оценки корутин
    loop = asyncio.get_running_loop()
    tasks = [to_rub(o[1], o[2]) for o in offers]
    rub_values = await asyncio.gather(*tasks)
    offers_sorted = [o for _, o in sorted(zip(rub_values, offers), key=lambda x: x[0])]

    lines = []
    for store, price, cur, url in offers_sorted:
        line = f"<a href=\"{url}\">{store}</a>: " + await fmt_price(price, cur)
        lines.append(line)

    text = f"💰 Актуальные цены для <b>{game_name}</b>:\n\n" + "\n".join(lines)
    await callback.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=offers_keyboard(game_id))


@router.callback_query(F.data == "price_back")
async def price_back(callback: types.CallbackQuery, state: FSMContext):
    cur_state = await state.get_state()
    if cur_state == PriceStates.waiting_for_game_choice.state:
        # Показываем ранее найденный список игр заново
        data = await state.get_data()
        games_dict = data.get("games", {})
        if games_dict:
            games_list = list(games_dict.items())
            try:
                await callback.message.edit_text("Выберите игру:", reply_markup=games_keyboard(games_list))
            except TelegramBadRequest as e:
                # сообщение и клавиатура уже такие – ничего не меняем
                if "message is not modified" not in str(e):
                    raise
        await callback.answer()
    else:
        # На шаге ввода названия / вне FSM – возвращаемся в меню
        await callback.message.delete()
        await state.clear()
        await base_handlers.cmd_main_menu(callback)
        await callback.answer()


@router.callback_query(F.data == "price_cancel", StateFilter("*"))
async def price_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    # Возврат в главное меню
    await base_handlers.cmd_main_menu(callback)
    await callback.answer() 