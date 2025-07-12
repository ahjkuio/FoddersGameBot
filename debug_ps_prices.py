#!/usr/bin/env python3
"""Быстрый скрипт для проверки get_offers PlayStation Store по разным регионам.
Запуск:
    python debug_ps_prices.py CUSA08519_00-REDEMPTIONFULL02
По умолчанию использует productId Red Dead Redemption 2, если аргумент не передан.
"""
import asyncio
import sys
from typing import List

from telegram_videogame_bot import ps_store_api as ps

REGIONS: List[str] = [
    "RU", "KZ", "PL", "UA", "TR", "IN", "BR", "AR", "US"
]

def game_id_from_pid(pid: str) -> str:
    if not pid.startswith("ps:"):
        return f"ps:{pid}"
    return pid

async def main():
    pid = sys.argv[1] if len(sys.argv) >= 2 else "EP1004-CUSA08519_00-REDEMPTIONFULL02"
    gid = game_id_from_pid(pid)

    for reg in REGIONS:
        try:
            offers = await ps.get_offers(gid, region=reg)
        except Exception as e:
            print(f"{reg}: error {e}")
            continue
        if not offers:
            print(f"{reg}: no offers")
            continue
        lbl, price, cur, url, plus_flag, _pltf, *_rest = offers[0]
        disc = None
        if len(offers[0]) >= 8:
            disc = offers[0][7]
        print(f"{reg}: {price} {cur}  plus={plus_flag}  disc={disc}  url={url}")

if __name__ == "__main__":
    asyncio.run(main()) 