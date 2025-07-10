"""PlayStation Store integration: поиск игр и получение цен через HTML JSON (__NEXT_DATA__).

search_games(query, region="US") -> [("ps:{productId}", title), ...]
get_offers(game_id, region="US") -> [(label, price, currency, url, ps_plus, platforms)]

ps_plus – True, если предложение связано с PS Plus (serviceBranding или upsellServiceBranding содержит PS_PLUS).
platforms – список строк, например ["PS4", "PS5"].
"""

from __future__ import annotations

import aiohttp
import json
import re
import os
from typing import List, Tuple, Dict, Any
from cachetools import TTLCache
from loguru import logger

# --- Caches ---
_SEARCH_CACHE: TTLCache[str, List[Tuple[str, str]]] = TTLCache(maxsize=1024, ttl=12 * 60 * 60)  # 12h
_PRODUCT_CACHE: TTLCache[Tuple[str, str], Dict[str, Any]] = TTLCache(maxsize=4096, ttl=30 * 60)  # 30m

# --- Region → locale mapping ---
_REGION_TO_LOCALE = {
    "RU": "ru-ru",
    "US": "en-us",
    "TR": "tr-tr",
    "BR": "pt-br",
    "AR": "es-ar",
    "IN": "en-in",   # India
    "UA": "uk-ua",  # Ukraine
    "KZ": "ru-ru",  # Kazakhstan (ru locale подходит)
    "PL": "pl-pl",  # Poland
}

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)"
}

# --- GraphQL (internal PSN API) settings ---
_PSN_COOKIE: str = os.getenv("PSN_COOKIE", "")
_GQL_ENDPOINT = "https://web.np.playstation.com/api/graphql/v1/op"
# публикатор запроса conceptRetrieveForCtasWithPrice (версии 1) — постоянный хэш
_GQL_HASH = "eab9d873f90d4ad98fd55f07b6a0a606e6b3925f2d03b70477234b79c1df30b5"

# Заголовки для GraphQL запросов. Cookie добавляем только если она задана.
_GQL_HEADERS = {
    "Accept": "application/json",
    "User-Agent": HEADERS["User-Agent"],
    "Origin": "https://store.playstation.com",
}
if _PSN_COOKIE:
    _GQL_HEADERS["Cookie"] = _PSN_COOKIE

_SEARCH_URL_TEMPLATE = "https://store.playstation.com/{locale}/search/{query}"
_PRODUCT_URL_TEMPLATE = "https://store.playstation.com/{locale}/product/{product_id}"
_GAMES_URL_TEMPLATE = "https://store.playstation.com/{locale}/games/{slug}"


def _slugify(title: str) -> str:
    """Грубая транслитерация в slug PlayStation /games/ URL."""
    import unicodedata, re
    txt = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    txt = re.sub(r"[^a-zA-Z0-9]+", "-", txt.strip()).strip("-").lower()
    return txt


async def _fetch_games_price(title: str, region: str) -> tuple[str | None, float | None]:
    """Пробует получить цену со страницы /games/<slug>. Возвращает (currency, value) либо (None, None)."""
    if not title:
        return None, None
    locale = _REGION_TO_LOCALE.get(region.upper(), "en-us")
    slug = _slugify(title)
    url = _GAMES_URL_TEMPLATE.format(locale=locale, slug=slug)
    try:
        async with aiohttp.ClientSession(headers={**HEADERS, "Accept-Language": locale}) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    return None, None
                html_page = await resp.text()
    except Exception:
        return None, None

    prices_found = re.findall(r"display-price\"[^>]*>([^<]{1,60})<", html_page)
    if not prices_found:
        prices_found = re.findall(r"displayPrice[^>]*>([^<]{1,60})<", html_page)
    if not prices_found:
        prices_found = re.findall(r'"priceOrText":"([^"\n]{1,40})"', html_page)

    best_val = 0.0
    best_txt = ""
    for cand in prices_found:
        m = re.search(r"[0-9]+(?:[\.,][0-9]{1,2})?", cand)
        if not m:
            continue
        try:
            val = float(m.group(0).replace(",", "."))
        except ValueError:
            continue
        if val > best_val:
            best_val = val
            best_txt = cand.strip()

    if not best_txt:
        return None, None

    curr = _currency_from_price(best_txt, region)
    return curr, best_val


# ---------------------------------------------------------------------------
# GraphQL price fetcher
# ---------------------------------------------------------------------------

async def _fetch_price_graphql(concept_id: str | None, region: str) -> tuple[str | None, float | None]:
    """Получает цену через внутренний GraphQL-эндпоинт. Возвращает (currency, value) либо (None, None).

    Требуется актуальная переменная окружения PSN_COOKIE с cookies, скопированными из браузера.
    """
    if not concept_id or not _PSN_COOKIE:
        return None, None

    logger.info(f"[PS] GraphQL conceptId={concept_id} region={region} cookie_sent={bool(_PSN_COOKIE)}")

    # Формируем URL аналогично тому, что шлёт браузер (GET с PersistedQuery).
    import aiohttp.helpers as _ah
    variables = json.dumps({"conceptId": str(concept_id)}, separators=(",", ":"))
    extensions = json.dumps({"persistedQuery": {"version": 1, "sha256Hash": _GQL_HASH}}, separators=(",", ":"))
    params = {
        "operationName": "conceptRetrieveForCtasWithPrice",
        "variables": variables,
        "extensions": extensions,
    }
    from urllib.parse import urlencode as _urlencode
    url = _GQL_ENDPOINT + "?" + _urlencode(params)

    try:
        async with aiohttp.ClientSession(headers={**_GQL_HEADERS, "Accept-Language": _REGION_TO_LOCALE.get(region.upper(), "en-us")}) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    return None, None
                data = await resp.json()
    except Exception as e:
        logger.info(f"[PS] GraphQL HTTP error: {e}")
        return None, None

    try:
        sku = data["data"]["concept"]["defaultSku"]
        price_block = sku.get("price") or {}
        actual = price_block.get("actualPrice") or {}
        val = actual.get("value") or actual.get("amount")
        cur = actual.get("currencyCode") or actual.get("currency")
        if val is None or cur is None:
            return None, None
        return cur, float(val)
    except Exception as e:
        logger.info(f"[PS] GraphQL parse error: {e}")
        return None, None

# ---------------------------------------------------------------------------
# Generic HTML price extractor (for /product/ and /games/)
# ---------------------------------------------------------------------------

_SYM_GROUP = r"R\$|US\$|ARS\$|ARS|MXN\$|CLP\$|Rs|TL|UAH|KZT|\$|€|£|₺|¥|₽|₹|₴|₸|zł|zl"

# Слова/фразы, по которым можно однозначно распознать DLC-товары (Gold Bars, Online, демо-версии)
_HTML_STOP_WORDS = [
    "gold bar", "gold bars", "red dead online", "online",         # en
    "barra de ouro", "barras de ouro",                              # pt-br
    "altın külçe",                                                   # tr
    "золот", "слитк",                                              # ru
    "ознайом", "демо",                                             # ua
    "trial", "demo",                                               # generic
    "deneme",                                                      # tr (trial)
]
_STOP_RE = re.compile("|".join(re.escape(w) for w in _HTML_STOP_WORDS), re.IGNORECASE)


def _collect_html_prices(html: str, region: str) -> List[Tuple[float, str]]:
    """Возвращает список (value, currency) всех цен, найденных в HTML."""
    pat = rf"(?:({_SYM_GROUP})\s*([0-9][0-9\s\u00A0\.,]{{0,10}})|([0-9][0-9\s\u00A0\.,]{{0,10}})\s*({_SYM_GROUP}))"
    rex = re.compile(pat)

    def _parse_float(txt: str) -> float | None:
        """Преобразует строку с ценой в float, корректно обрабатывая тысячи '.'/',' и десятичные."""
        if not txt:
            return None
        buf = txt.replace("\u00A0", "").replace(" ", "")
        # Если и точка, и запятая – определяем десятичный разделитель по последнему символу
        if "," in buf and "." in buf:
            last_dot = buf.rfind('.')
            last_comma = buf.rfind(',')
            if last_comma > last_dot:
                dec_pos = last_comma
                dec_char = ','
            else:
                dec_pos = last_dot
                dec_char = '.'
            int_part = re.sub(r"[.,]", "", buf[:dec_pos])
            dec_part = buf[dec_pos + 1:]
            if not dec_part.isdigit():
                dec_part = "0"
            buf_norm = f"{int_part}.{dec_part}"
        elif "," in buf:
            # либо 1.234 либо 39,99
            last_comma = buf.rfind(',')
            dec_len = len(buf) - last_comma - 1
            if dec_len == 2:
                int_part = re.sub(r",", "", buf[:last_comma])
                dec_part = buf[last_comma + 1:]
                buf_norm = f"{int_part}.{dec_part}"
            else:
                buf_norm = buf.replace(',', '')
        else:
            buf_norm = buf
        try:
            return float(buf_norm)
        except ValueError:
            return None

    res: list[Tuple[float, str]] = []
    for m in rex.finditer(html):
        sym = m.group(1) or m.group(4)
        num_raw = m.group(2) or m.group(3)
        if not (sym and num_raw):
            continue

        # контекст 120 символов вокруг цены – если нашли стоп-слово, пропускаем
        ctx_start = max(0, m.start() - 120)
        ctx_end   = min(len(html), m.end() + 120)
        ctx = html[ctx_start:ctx_end]
        if _STOP_RE.search(ctx):
            continue

        val = _parse_float(num_raw)
        if val is None:
            continue
        cur = _currency_from_price(sym, region)
        res.append((val, cur))
    return res


def _select_full_price(prices: List[Tuple[float, str]], currency: str, *, deluxe_mode: bool) -> float | None:
    """Для стандартных изданий берёт минимальную цену > порога.
    Для Deluxe/Ultimate/Bundles – наоборот максимальную (но тоже > порога, если есть)."""
    if not prices:
        return None
    values = [v for v, cur in prices if cur == currency]
    if not values:
        # если символы смешаны, просто берём макс по всем
        values = [v for v, _ in prices]
        return max(values)

    dep_limit = {
        "USD": 30,
        "UAH": 500,
        "TRY": 500,
        "ARS": 5000,
        "INR": 700,
        "KZT": 9000,
        "BRL": 80,
        "PLN": 100,
        "RUB": 700,
    }.get(currency, 0)

    above = [v for v in values if v > dep_limit]

    if deluxe_mode:
        # Для Deluxe-/Ultimate-изданий берём максимальную среди «не депозитных»
        return max(above) if above else max(values)

    # --- Standard Edition ---
    if not above:
        # остались только (возможно) депозитные – берём максимальное, чтобы отсеять $ 79.99 и пр.
        return max(values)

    # Убираем дубликаты (они мешают сравнению соседей)
    uniq = sorted(set(above))

    if len(uniq) == 1:
        return uniq[0]

    # Отбрасываем все начальные элементы, которые меньше половины следующего – это почти наверняка DLC / виртуальная валюта
    idx = 0
    while idx + 1 < len(uniq) and uniq[idx] * 1.8 <= uniq[idx + 1]:
        idx += 1  # пропускаем маленькую цену

    # Если всё отбросили (маловероятно) – берём последнюю оставшуюся
    clean = uniq[idx:]
    if not clean:
        clean = [uniq[-1]]

    if deluxe_mode:
        return max(clean)

    # Standard edition → берём минимальную из «чистого» списка
    return clean[0]


_CURRENCY_SYMBOL_MAP = [
    ("R$", "BRL"),
    ("US$", "USD"),
    ("ARS$", "ARS"),
    ("ARS", "ARS"),
    ("MXN$", "MXN"),
    ("CLP$", "CLP"),
    ("Rs", "INR"),
    ("TL", "TRY"),
    ("UAH", "UAH"),
    ("KZT", "KZT"),
    ("€", "EUR"),
    ("£", "GBP"),
    ("₺", "TRY"),
    ("¥", "CNY"),
    ("₽", "RUB"),
    ("₹", "INR"),
    ("₴", "UAH"),
    ("₸", "KZT"),
    ("zł", "PLN"),
    ("zl", "PLN"),
    ("$", "USD"),  # самый общий символ – в конце
]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _extract_next_data(html: str) -> Dict[str, Any] | None:
    """Извлекает JSON из тега <script id="__NEXT_DATA__">...</script>."""
    m = re.search(r"<script id=\"__NEXT_DATA__\"[^>]*>(\{.*?\})</script>", html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception as e:
        logger.warning(f"[PS] JSON decode error: {e}")
        return None


def _currency_from_price(price_str: str, region: str) -> str:
    """Определяет трёхбуквенный код валюты по её символу/тексту.

    Особый случай – одиночный символ "$":
    он используется и в US (USD), и в странах Латинской Америки (ARS, CLP, MXN и др.).
    Поэтому, если нашли только "$", смотрим на регион.
    """
    for symbol, cur in _CURRENCY_SYMBOL_MAP:
        if symbol in price_str:
            if symbol == "$":
                return {
                    "AR": "ARS",
                    "CL": "CLP",
                    "MX": "MXN",
                    "US": "USD",
                }.get(region, "USD")
            return cur
    # fallback by region
    return {
        "RU": "RUB",
        "TR": "TRY",
        "BR": "BRL",
        "AR": "ARS",
        "IN": "INR",
        "UA": "UAH",
        "KZ": "KZT",
        "PL": "PLN",
    }.get(region, "USD")


async def search_games(query: str, *, region: str = "US", limit: int = 40) -> List[Tuple[str, str]]:
    """Поиск игр в PS Store через публичную HTML-страницу search/QUERY."""
    if not query:
        return []
    region = region.upper()
    locale = _REGION_TO_LOCALE.get(region, "en-us")
    cache_key = f"{locale}:{query.lower()}"
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key][:limit]

    url = _SEARCH_URL_TEMPLATE.format(locale=locale, query=aiohttp.helpers.quote(query))
    try:
        async with aiohttp.ClientSession(headers={**HEADERS, "Accept-Language": locale}) as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status != 200:
                    logger.info(f"[PS] search HTTP {resp.status}")
                    _SEARCH_CACHE[cache_key] = []
                    return []
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[PS] search error: {e}")
        _SEARCH_CACHE[cache_key] = []
        return []

    data = _extract_next_data(html)
    if not data:
        _SEARCH_CACHE[cache_key] = []
        return []

    apollo = data.get("props", {}).get("apolloState", {})

    results: List[Tuple[str, str]] = []
    for key, item in apollo.items():
        if not key.startswith("Product:"):
            continue
        title = item.get("name")
        pid = item.get("id") or key.split(":", 1)[1]
        if not title or not pid:
            continue
        game_id = f"ps:{pid}"
        results.append((game_id, title))
        # сохраняем объект продукта для зоны региона
        _PRODUCT_CACHE[(region, game_id)] = item

        if len(results) >= limit:
            break

    _SEARCH_CACHE[cache_key] = results
    return results


async def _fetch_html_proxy(url: str, _region: str, locale: str, *, tries: int = 1) -> str | None:
    """Скачивает HTML напрямую (прокси отключены). Оставил сигнатуру для совместимости."""
    logger.info(f"[PS] HTML fetch {url}")
    try:
        async with aiohttp.ClientSession(headers={**HEADERS, "Accept-Language": locale}) as session:
            async with session.get(url, timeout=8) as resp:
                logger.info(f"[PS] HTML status {resp.status} {url}")
                if resp.status == 200:
                    return await resp.text()
    except Exception as e:
        logger.info(f"[PS] HTML error {e} for {url}")
    return None


async def _fetch_product(pid: str, region: str) -> Dict[str, Any] | None:
    """Запрос HTML страницы продукта для получения JSON."""
    locale = _REGION_TO_LOCALE.get(region, "en-us")
    url = _PRODUCT_URL_TEMPLATE.format(locale=locale, product_id=pid)
    html = await _fetch_html_proxy(url, region, locale)
    if html is None:
        return None

    data = _extract_next_data(html)
    if not data:
        return None

    # Результирующий объект товара, который найдём ниже,
    # дополним исходным HTML, чтобы повторно не скачивать его при get_offers.
    # Это ускоряет процесс и повышает шанс получить цены, если второй запрос сорвётся.
    product_html: str | None = html

    apollo = data.get("props", {}).get("apolloState", {})
    for key, item in apollo.items():
        if key.startswith("Product:") and item.get("id") == pid:
            # дополним conceptId, если он отсутствует
            if "conceptId" not in item:
                concept = item.get("concept")
                if isinstance(concept, dict):
                    cid = concept.get("id")
                    if cid:
                        item["conceptId"] = cid
                elif isinstance(concept, str) and concept.startswith("Concept:"):
                    item["conceptId"] = concept.split(":", 1)[1]

            # Кэшируем HTML внутри объекта, чтобы им могли воспользоваться другие функции.
            if product_html is not None:
                item["__html"] = product_html

            return item
    return None


async def get_offers(game_id: str, region: str = "US", _depth: int = 0) -> List[Tuple]:
    """Возвращает [(store_label, price, currency, url, ps_plus, platforms, deposit_flag)].

    deposit_flag == True, если полученная цена является задатком (депозитом) при предзаказе
    и полная стоимость пока скрыта PlayStation Store.
    """
    if not game_id.startswith("ps:"):
        return []

    region = region.upper()
    cache_key = (region, game_id)
    product = _PRODUCT_CACHE.get(cache_key)

    if product is None:
        pid = game_id.split(":", 1)[1]
        product = await _fetch_product(pid, region)
        if product is None:
            # Фоллбэк: попытаться найти продукт по имени (если глубина 0)
            if _depth == 0:
                # Берём название из любого кэша, если есть
                title_guess = None
                for (_r, gid), obj in _PRODUCT_CACHE.items():
                    if gid == game_id:
                        title_guess = obj.get("name")
                        break
                if not title_guess:
                    # как крайний случай – по id без префикса
                    title_guess = pid.split("_", 1)[0]
                candidates = await search_games(title_guess, region=region, limit=1)
                if candidates:
                    return await get_offers(candidates[0][0], region, _depth=1)
            return []
        _PRODUCT_CACHE[cache_key] = product

    # --- Platforms ---
    platforms = product.get("platforms") or []
    if not platforms:
        pid_guess = product.get("id", "")
        if not pid_guess and game_id.startswith("ps:"):
            pid_guess = game_id.split(":", 1)[1]
        if "PPSA" in pid_guess or "PUSA" in pid_guess:
            platforms = ["PS5"]
        elif "CUSA" in pid_guess:
            platforms = ["PS4"]

    # --- Price ---
    price_info = product.get("price") or {}
    is_free = price_info.get("isFree", False)

    # Инициализация, чтобы переменные были доступны далее в любом случае
    base_price_str: str | None = None
    disc_price_str: str | None = None

    if is_free:
        price_val = 0.0
        currency = "FREE"
        deposit_flag = False # Ensure it's False for free games
    else:
        base_price_str = price_info.get("basePrice")
        disc_price_str = price_info.get("discountedPrice")

        # --- Определяем, не является ли скидка «PS Plus only» ---
        def _has_plus_branding() -> bool:
            for arr in (price_info.get("serviceBranding"), price_info.get("upsellServiceBranding")):
                if arr and any("PLUS" in s for s in arr):
                    return True
            return False

        plus_branding_flag = _has_plus_branding()

        # Если есть цена со скидкой и она НЕ относится только к PS Plus ‑ используем её,
        # иначе берём базовую.
        price_str: str = ""
        if disc_price_str and not plus_branding_flag:
            price_str = disc_price_str
        elif base_price_str:
            price_str = base_price_str
        elif disc_price_str:
            price_str = disc_price_str

        # --- если цены нет в HTML-JSON, пробуем GraphQL сразу ---
        if not price_str and product.get("conceptId") and _PSN_COOKIE:
            gql_cur, gql_val = await _fetch_price_graphql(str(product.get("conceptId")), region)
            if gql_val is not None and gql_cur:
                currency = gql_cur
                price_val = gql_val
                price_str = f"{gql_val} {gql_cur}"
                # сразу прерываем дальнейший разбор (депозит невозможен)
                deposit_flag = False
            # если всё равно пусто, продолжим обычный путь (slug/HTML)

        if not price_str:
            # Пытаемся получить цену со страницы /games/<slug>
            g_cur, g_val = await _fetch_games_price(product.get("name", ""), region)
            if g_cur and g_val is not None:
                currency = g_cur
                price_val = g_val
                price_str = f"{g_val} {g_cur}"
            else:
                # HTML-парсер ещё может вытащить цену ниже, не выходим досрочно
                price_val = 0.0
                price_str = "0"
        currency = _currency_from_price(price_str, region)
        # --- парсим число с помощью той же логики, что и в _collect_html_prices ---
        cleaned = re.sub(r"[^0-9.,\s\u00A0]", "", price_str)
        cleaned = re.sub(r"[\s\u00A0]", "", cleaned)

        def _safe_parse(txt: str) -> float | None:
            if not txt:
                return None
            if "," in txt and "." in txt:
                last_dot = txt.rfind('.')
                last_comma = txt.rfind(',')
                if last_comma > last_dot:
                    int_part = re.sub(r"[.,]", "", txt[:last_comma])
                    dec_part = txt[last_comma + 1:]
                    txt_norm = f"{int_part}.{dec_part}"
                else:
                    int_part = re.sub(r"[.,]", "", txt[:last_dot])
                    dec_part = txt[last_dot + 1:]
                    txt_norm = f"{int_part}.{dec_part}"
            elif "," in txt:
                last_comma = txt.rfind(',')
                if len(txt) - last_comma - 1 == 2:
                    int_part = txt[:last_comma].replace(',', '')
                    dec_part = txt[last_comma + 1:]
                    txt_norm = f"{int_part}.{dec_part}"
                else:
                    txt_norm = txt.replace(',', '')
            else:
                txt_norm = txt
            try:
                return float(txt_norm)
            except ValueError:
                return None

        parsed_val = _safe_parse(cleaned)
        if parsed_val is None:
            logger.warning(f"[PS] cannot parse price '{price_str}' for {game_id}")
            return []
        price_val = parsed_val

        # --- попытка уточнить через GraphQL (если есть conceptId и куки) ---
        if product.get("conceptId") and _PSN_COOKIE:
            gql_cur, gql_val = await _fetch_price_graphql(str(product.get("conceptId")), region)
            if gql_val and (gql_val > price_val * 1.3):
                price_val = gql_val
                currency = gql_cur or currency
                deposit_flag = False

        # Если мы уже используем обычную скидочную (не Plus) цену, дополнительно проверять HTML не нужно –
        # иначе можно случайно заменить её на старую базовую.
        skip_html_override = (disc_price_str and price_str == disc_price_str and not plus_branding_flag)

        # Если цена выглядит подозрительно низкой (депозит) и мы НЕ на скидке – сверяемся с HTML.
        html_price_val: float | None = None
        html_price_str: str = ""
        try:
            title_lc = (product.get("name" , "") or "").lower()
            deluxe_mode = any(x in title_lc for x in ("deluxe", "ultimate", "gold", "premium", "bundle", "director"))

            locale = _REGION_TO_LOCALE.get(region, "en-us")
            html_page = None

            if not skip_html_override:
                # Сначала пробуем повторно скачать HTML
                html_url = _PRODUCT_URL_TEMPLATE.format(locale=locale, product_id=product.get("id"))
                html_page = await _fetch_html_proxy(html_url, region, locale)

                # Если не удалось (таймаут / блокировка), берём HTML, сохранённый при _fetch_product
                if not html_page:
                    html_page = product.get("__html")

            if html_page and not skip_html_override:
                # Расширенный парсинг: берём максимальную цену из HTML
                prices = _collect_html_prices(html_page, region)
                if prices:
                    full_price = _select_full_price(prices, currency, deluxe_mode=deluxe_mode)
                    if full_price is not None:
                        html_price_val = full_price
                        # определяем валюту, соответствующую выбранной цене
                        html_cur = currency
                        for v, cur_sym in prices:
                            if abs(v - full_price) < 0.01:
                                html_cur = cur_sym
                                break
                        html_price_str = f"{full_price} {html_cur}"
                        currency = html_cur
        except Exception as _e:
            logger.info(f"[PS] second html check error: {_e}")

        if html_price_val and html_price_val > price_val * 1.5:
            price_val = html_price_val
            price_str = html_price_str
            currency = _currency_from_price(price_str, region)
            deposit_flag = False

        # --- предварительная оценка: похоже на депозит? ---
        deposit_flag = False

        _DEP_THRESH = {
            "USD": 30,
            "UAH": 500,
            "TRY": 500,
            "ARS": 5000,
            "INR": 700,
            "KZT": 9000,
            "BRL": 80,
            "PLN": 100,
            "RUB": 700,
        }

        dep_limit = _DEP_THRESH.get(currency, None)
        # Депозиты встречаются в основном в AR / KZ; в остальных регионах низкая цена чаще означает скидку.
        if dep_limit and price_val < dep_limit and region in {"AR", "KZ"}:
            deposit_flag = True

        # --- спец-правило для AR / KZ: если ещё депозит и есть USD цена >30 – берём её ---
        if deposit_flag and region in {"AR", "KZ"}:
            usd_candidates = [v for v, cur in prices if cur == "USD" and v > 30]
            if usd_candidates:
                best_usd = min(usd_candidates)
                price_val = best_usd
                currency = "USD"
                deposit_flag = False

        # fallback только если подозреваем депозит && первая попытка
        if deposit_flag and _depth == 0:
            # Пробуем запросить тот же товар в US: там часто видна полная цена
            us_offer = await get_offers(game_id, region="US", _depth=1)
            if us_offer:
                _lbl, us_price, us_cur, *_ = us_offer[0]
                if us_price > price_val * 1.5:
                    price_val = us_price
                    currency = us_cur
                    deposit_flag = False  # заменили депозит на полную цену

        # Поиск альтернативных SKU (PS5-версий, Deluxe и т.д.) убран – слишком медленно
        # и часто приводит к неверному соответствию (Director's Cut вместо On The Beach).

    # --- депозит (предзаказ) ---
    # deposit_flag уже выставлен выше; можно скорректировать при необходимости

    # --- PS Plus flag ---
    plus_flag = False
    for arr in (price_info.get("serviceBranding"), price_info.get("upsellServiceBranding")):
        if arr and any("PLUS" in s for s in arr):
            plus_flag = True
            break

    locale = _REGION_TO_LOCALE.get(region, "en-us")
    url = _PRODUCT_URL_TEMPLATE.format(locale=locale, product_id=product.get("id"))

    # --- Цена со скидкой PS Plus (если отличается) ---
    discount_val: float | None = None
    if plus_flag and disc_price_str and disc_price_str != base_price_str:
        # Парсим disc_price_str аналогично основной цене
        _disc_raw = re.sub(r"[^0-9.,\s\u00A0]", "", disc_price_str)
        _disc_raw = re.sub(r"[\s\u00A0]", "", _disc_raw)
        _disc_raw = _disc_raw.replace(",", ".")
        try:
            discount_val = float(_disc_raw)
        except ValueError:
            discount_val = None

    label = "PlayStation Store" if region == "RU" else f"PlayStation Store {region}"
    tup: list = [label, price_val, currency, url, plus_flag, platforms, deposit_flag]
    if discount_val and abs(discount_val - price_val) > 0.01:
        tup.append(discount_val)

    return [tuple(tup)]


async def list_editions(game_id: str, region: str = "US", limit: int = 20) -> List[Tuple[str, str]]:
    """Возвращает список (game_id, title) альтернативных изданий той же игры.

       Алгоритм простой:
        1. Получаем название базового товара (через кэш/запрос).
        2. Выполняем search_games по этому названию – PlayStation в поисковой выдаче обычно
           показывает все связанные SKU (Standard, Deluxe, Bundle, Director's Cut и т.д.).
        3. Ограничиваем количество результатов параметром *limit*.

        В ответе только id и заголовок – подробности (цена и т.д.) будут получены позднее
        через get_offers для конкретного выбора пользователя.
        """
    if not game_id.startswith("ps:"):
        return []

    region = region.upper()
    cache_key = (region, game_id)
    product = _PRODUCT_CACHE.get(cache_key)
    if product is None:
        pid = game_id.split(":", 1)[1]
        product = await _fetch_product(pid, region)
        if product:
            _PRODUCT_CACHE[cache_key] = product
    if not product:
        return []

    base_title: str = product.get("name", "")
    if not base_title:
        return []

    # Выполняем поиск
    candidates = await search_games(base_title, region=region, limit=limit)

    # Некоторые результаты могут совпадать с исходным id – подвинем его в начало списка
    # и уберём точные дубликаты.
    seen: set[str] = set()
    editions: list[Tuple[str, str]] = []
    for gid, title in candidates:
        if gid in seen:
            continue
        seen.add(gid)
        editions.append((gid, title))

    # Перемещаем базовый id в начало (если есть)
    for i, (gid, _t) in enumerate(editions):
        if gid == game_id:
            base = editions.pop(i)
            editions.insert(0, base)
            break

    return editions 