"""Microsoft Store (Xbox / PC) helper.

Минимальная заглушка. Будет доработана для работы с DisplayCatalog API.
Поддерживает флаг game_pass в ответах get_offers, который позже будет отображаться ботом.

search_games(query) -> [("ms:{productId}", title), ...]
get_offers(game_id, region) -> [(store_label, price, currency, url, game_pass)]
На первых порах, чтобы не ломать существующий формат, game_pass просто
добавляется в label («Microsoft Store (Game Pass)»).
"""
from __future__ import annotations

import aiohttp
import re, json
from typing import List, Tuple, Any
from loguru import logger
from cachetools import TTLCache

_SEARCH_CACHE: TTLCache[str, List[Tuple[str, str]]] = TTLCache(maxsize=1024, ttl=12 * 60 * 60)  # 12h
_PRICE_CACHE: TTLCache[str, Tuple[str, float, str, str]] = TTLCache(maxsize=4096, ttl=30 * 60)  # 30m

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)"
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_XBOX_SEARCH_URL = "https://www.xbox.com/{locale}/search?q={query}&cat=games"

# Сопоставление регионов Xbox локациям
_REGION_TO_LOCALE = {
    "RU": "ru-ru",
    "US": "en-us",
    "TR": "tr-tr",
    "BR": "pt-br",
    "AR": "es-ar",
    "IN": "en-in",
    "UA": "uk-ua",
    "KZ": "ru-kz",
    "PL": "pl-pl",
}


def _extract_product_summaries(html: str) -> dict[str, dict]:
    """Извлекает объект productSummaries из скрипта на странице xbox.com.

    Структура HTML одинакова как для результатов поиска, так и для страниц
    конкретных игр: внутри большого JSON-объекта присутствует ключ
    "productSummaries". Мы ищем начало этого объекта и затем счётчиком фигурных
    скобок находим его конец, чтобы безопасно вырезать корректную подстроку
    и распарсить её через json.loads().
    """

    start_key = '"productSummaries":'
    start = html.find(start_key)
    if start == -1:
        return {}

    # позиция первой открывающей скобки
    brace_open = html.find('{', start)
    if brace_open == -1:
        return {}

    depth = 1
    i = brace_open + 1
    length = len(html)
    while i < length and depth:
        ch = html[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        i += 1

    if depth != 0:
        return {}

    json_str = html[brace_open:i]
    try:
        return json.loads(json_str)
    except Exception:
        return {}


async def search_games(query: str, limit: int = 20, *, region: str = "US") -> List[Tuple[str, str]]:
    """Поиск через публичную HTML-страницу xbox.com/search."""

    if not query:
        return []

    locale = _REGION_TO_LOCALE.get(region.upper(), "en-us")
    cache_key = f"{locale}:{region}:{query.lower()}"
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key][:limit]

    url = _XBOX_SEARCH_URL.format(locale=locale, query=aiohttp.helpers.quote(query))
    headers = {**HEADERS, "Accept-Language": locale, "x-market": region}

    results: List[Tuple[str, str]] = []
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"[MS] search HTTP {resp.status}")
                    _SEARCH_CACHE[cache_key] = []
                    return []
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[MS] search error: {e}")
        _SEARCH_CACHE[cache_key] = []
        return []

    summaries = _extract_product_summaries(html)
    for pid, info in summaries.items():
        title = info.get("title") or info.get("productTitle")
        if not title:
            continue
        # Если игра доступна хотя бы на одной платформе (PC или Xbox), оставляем
        results.append((f"ms:{pid}", title))
        if len(results) >= limit:
            break

    _SEARCH_CACHE[cache_key] = results
    return results


async def get_offers(game_id: str, region: str = "US") -> List[Tuple[Any, ...]]:
    """Парсит ту же выдачу Xbox для получения цены и флага Game Pass."""

    if not game_id.startswith("ms:"):
        return []

    pid = game_id.split(":", 1)[1]
    locale = _REGION_TO_LOCALE.get(region.upper(), "en-us")
    url = f"https://www.xbox.com/{locale}/games/store/x/{pid}"
    headers = {**HEADERS, "Accept-Language": locale, "x-market": region}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.info(f"[MS] price HTTP {resp.status} for {pid}")
                    return []
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[MS] price error: {e}")
        return []

    summaries = _extract_product_summaries(html)
    info = summaries.get(pid)
    if not info:
        return []

    # --- Price extraction ---
    sp = info.get("specificPrices", {})
    purchaseables = sp.get("purchaseable", [])
    discount_prices = sp.get("discountPrices", [])

    def _pick_best(entry_list: list[dict[str, str]]) -> tuple[str | None, str | None]:
        """Возвращает (price_text, currency). Ищет среди listPrice, msrp, displayPrice etc."""
        price_keys = ("listPrice", "msrp", "displayPrice", "price", "listPriceDisplay")
        for ent in entry_list:
            price_txt = ""
            for k in price_keys:
                v = ent.get(k)
                if v:
                    price_txt = str(v)
                    break
            if price_txt and not str(price_txt).startswith("0"):
                curr = ent.get("currencyCode") or ent.get("currency") or ""
                return price_txt, curr

        # не нашли ненулевую – ищем хотя бы что-то
        if entry_list:
            ent = entry_list[0]
            price_txt = ""
            for k in price_keys:
                v = ent.get(k)
                if v:
                    price_txt = str(v)
                    break
            curr = ent.get("currencyCode") or ent.get("currency") or ""
            return price_txt, curr

        return None, None

    # --- Собираем кандидатов, отделяя обычные цены и скидки GP ---
    Candidate = tuple[str, str, bool]  # price_text, currency, is_gp_price
    candidates: list[Candidate] = []
    for lst in (purchaseables, discount_prices):
        for ent in lst:
            pt = None
            for k in ("listPrice", "msrp", "displayPrice", "price", "listPriceDisplay"):
                v = ent.get(k)
                if v not in (None, ""):
                    pt = str(v)
                    break
            if not pt:
                continue
            cur = ent.get("currencyCode") or ent.get("currency") or ""
            elig = ent.get("eligibilityInfo", {})
            gp_entry = (elig.get("type") == "GamePass")
            candidates.append((pt, cur, gp_entry))

    logger.info(f"[Xbox] {pid} {region} raw candidates: {candidates}")

    # Выбираем максимальную числовую цену >0
    price_text: str | None = None   # обычная (наибольшая)
    discount_text: str | None = None  # минимальная GP-скидка
    currency: str | None = None
    max_regular = 0.0
    min_gp = float("inf")

    for pt, cur, gp in candidates:
        cleaned = re.sub(r"[^0-9.,]", "", str(pt))
        raw_val = cleaned.replace(',', '.').replace(' ', '')
        try:
            val = float(raw_val)
        except ValueError:
            continue

        if gp:
            if val < min_gp:
                min_gp = val
                discount_text = pt
        else:
            if val > max_regular:
                max_regular = val
                price_text = pt
        if not currency:
            currency = cur

    if not currency:
        _REGION_TO_CURRENCY = {
            "RU": "RUB", "US": "USD", "TR": "TRY", "BR": "BRL", "AR": "ARS",
            "IN": "INR", "UA": "UAH", "KZ": "KZT", "PL": "PLN",
        }
        currency = _REGION_TO_CURRENCY.get(region.upper(), "USD")

    props = info.get("properties", {})
    game_pass_flag = bool(
        props.get("isGamePass")
        or props.get("isGamePassWithCatalog")
        or info.get("includedWithPassesProductIds")
        or discount_text is not None
    )
    if price_text is None and discount_text is None:
        label = "Xbox Store" if region.upper() == "RU" else f"Xbox Store {region.upper()}"
        hardware = info.get("availableOn") or []
        if game_pass_flag:
            return [(label, 0.0, "FREE", url, True, hardware)]
        return []

    # --- parse price number ---
    price_clean = re.sub(r"[^0-9.,\s\u00A0]", "", str(price_text or discount_text), flags=re.UNICODE)
    price_clean = price_clean.replace("\u00A0", " ").strip()
    price_clean = price_clean.replace(" ", "")
    raw = price_clean.replace(",", ".")

    def _to_float(txt: str | None) -> float | None:
        if not txt:
            return None
        c = re.sub(r"[^0-9.,\s\u00A0]", "", txt, flags=re.UNICODE)
        c = c.replace("\u00A0", " ").strip().replace(" ", "")
        c = c.replace(',', '.')
        try:
            return float(c)
        except ValueError:
            return None

    price_val = _to_float(price_text)
    discount_val = _to_float(discount_text)
    if price_val is None:
        price_val = max_regular if max_regular else discount_val

    logger.info(f"[Xbox] {pid} {region} result base={price_val} discount={discount_val} gp={game_pass_flag}")

    label = "Xbox Store" if region.upper() == "RU" else f"Xbox Store {region.upper()}"
    hardware = info.get("availableOn") or []
    tup = [
        label,
        price_val,
        currency,
        url,
        game_pass_flag,
        hardware,
    ]
    if discount_val is not None and abs(discount_val - price_val) > 0.01:
        tup.append(discount_val)

    return [tuple(tup)] 