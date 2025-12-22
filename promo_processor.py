import asyncio
import re
import json
import aiohttp
from decimal import Decimal
from refresh_tokens import get_valid_access_token, refresh_by_refresh_token
from telegram_bot import RAM_DATA, ACTIVE_NOMINALS, send_summary, chat_ids
from config import API_URL_PROMO_ACTIVATE, API_URL_BET

print("PROMO reads RAM_DATA id:", id(RAM_DATA))

# -------------------------
# Форматирование ошибок и статусов
# -------------------------
def format_promo_status(resp):
    # -------------------------
    # 3️⃣ Нет ответа от сервера
    # -------------------------
    if resp is None:
        return "Ошибка API (нет ответа)"

    # -------------------------
    # Получаем стандартные поля
    # -------------------------
    error = resp.get("error", "")
    payload = resp.get("payload", {})

    # -------------------------
    # 1️⃣ Успешная активация
    # -------------------------
    if resp.get("success") and resp.get("data", {}).get("isActivate"):
        return "Активирован"

    # -------------------------
    # 2️⃣ Известные ошибки промо
    # -------------------------
    if error == "ALREADY_ACTIVATED":
        return "Был активирован ранее"
    elif error == "LIMIT":
        return "Превышен лимит активаций"
    elif error == "DEPOSIT_CONDITION_ERROR":
        return "Недостаточно депозита"
    elif error == "NOT_FOUND":
        return "Промокод не найден"
    elif error == "NOT_ENOUGH_BALANCE":
        return "Не сделали ставку с прошлого промо"
    elif error == "NOT_VERIFIED_CAPTCHA":
        return "Ограничения аккаунта (минимальный номинал)"

    # -------------------------
    # Любая другая "нестандартная" ошибка
    # -------------------------
    return f"Ошибка | {json.dumps(resp, ensure_ascii=False)}"

# -------------------------
# Получение персональных активных номиналов с проверкой suspended
# -------------------------
def get_user_nominals(chat_id):
    user_data = RAM_DATA.get(chat_id)
    if not user_data:
        RAM_DATA[chat_id] = {
            "active_nominals": {Decimal(str(n)): True for n in ACTIVE_NOMINALS},
            "currency": "USD",
            "suspended": False
        }
        user_data = RAM_DATA[chat_id]
    return user_data["active_nominals"]

def get_user_currency(chat_id):
    user_data = RAM_DATA.get(chat_id)
    return user_data.get("currency", "USD") if user_data else "USD"

def is_user_active(chat_id):
    """Проверка: пользователь не приостановлен"""
    user_data = RAM_DATA.get(chat_id)
    return not user_data.get("suspended", False) if user_data else True
# -------------------------
# Парсер промокодов
# -------------------------
def parse_promo_codes(message: str):
    results = []
    for line in message.splitlines():
        match = re.search(r'(\d+(?:\.\d+)?)\$\s*.*—\s*([A-Za-z0-9]{4,})', line)
        if match:
            nominal = Decimal(match.group(1)).quantize(Decimal("0.01"))
            results.append({
                "promo_code": match.group(2),
                "nominal": nominal
            })
    return results

# -------------------------
# Асинхронный контейнер для одного аккаунта
# -------------------------
async def account_container(chat_id, promo_items):
    if not is_user_active(chat_id):
        print(f"[PROMO] chat_id {chat_id} — пользователь приостановлен")
        return

    user_nominals = get_user_nominals(chat_id)
    enabled_promos = [
        item for item in promo_items
        if user_nominals.get(item["nominal"], True)
    ]

    access_token = get_valid_access_token(str(chat_id))
    if not access_token:
        print(f"[PROMO] chat_id {chat_id} — нет access токена")
        return

    user_summary = []
    currency = get_user_currency(chat_id)
    bet_amount = 0.1 if currency == "USD" else 10.5

    def no_money_on_bet(resp_bet):
        return resp_bet.get("error") == "" and resp_bet.get("payload") == {}

    i = 0
    while i < len(enabled_promos):
        item = enabled_promos[i]
        promo = item["promo_code"]
        nominal = item["nominal"]

        # -------------------------
        # 1️⃣ Активация промо
        # -------------------------
        resp = await activate_promo(chat_id, promo, access_token)
        status = format_promo_status(resp)
        
        # 🔴 Новый блок: проверка на отсутствие ответа от API
        if resp is None or not resp:
            user_summary.append({
                "promo_code": promo,
                "nominal": float(nominal),
                "status": "Ошибка API (нет ответа)"
            })
            print(f"[PROMO] chat_id {chat_id} — API не ответил, стоп")
            break  # останавливаем обработку всех последующих промокодов
        

        # 🔁 токен умер → обновляем
        if resp.get("error") == "Auth token not found!":
            tokens = RAM_DATA.get(chat_id)
            if tokens and refresh_by_refresh_token(str(chat_id), tokens.get("refresh_token")):
                access_token = get_valid_access_token(str(chat_id))
                continue
            break

        # -------------------------
        # 2️⃣ Нужно сделать ставку ДО активации
        # -------------------------
        if status == "Не сделали ставку с прошлого промо":
            resp_bet = await make_bet(chat_id, promo, access_token, bet_amount)

            if no_money_on_bet(resp_bet):
                user_summary.append({
                    "promo_code": promo,
                    "nominal": float(nominal),
                    "status": "Не сделали ставку с прошлого промо\nНедостаточно денег для ставки"
                })
                print(f"[PROMO] chat_id {chat_id} — нет денег, стоп")
                break

            # ставка успешна → пробуем ЭТОТ ЖЕ промо ещё раз
            continue

        # -------------------------
        # 3️⃣ Промо активирован → ОБЯЗАТЕЛЬНА ставка
        # -------------------------
        if status == "Активирован":
            resp_bet = await make_bet(chat_id, promo, access_token, bet_amount)

            if no_money_on_bet(resp_bet):
                user_summary.append({
                    "promo_code": promo,
                    "nominal": float(nominal),
                    "status": "Активирован\nНедостаточно денег для ставки"
                })
                print(f"[PROMO] chat_id {chat_id} — нет денег, стоп")
                break

            user_summary.append({
                "promo_code": promo,
                "nominal": float(nominal),
                "status": "Активирован"
            })
            i += 1
            continue

        # -------------------------
        # 4️⃣ Финальные статусы промо (без ставок)
        # -------------------------
        if status in [
            "Был активирован ранее",
            "Превышен лимит активаций",
            "Недостаточно депозита",
            "Промокод не найден"
        ]:
            user_summary.append({
                "promo_code": promo,
                "nominal": float(nominal),
                "status": status
            })
            i += 1
            continue

        # -------------------------
        # 5️⃣ Всё остальное
        # -------------------------
        user_summary.append({
            "promo_code": promo,
            "nominal": float(nominal),
            "status": status
        })
        i += 1

    # -------------------------
    # Отправка сводки
    # -------------------------
    if user_summary:
        user_summary.sort(key=lambda x: x["nominal"])
        await send_summary(chat_id, user_summary)

# -------------------------
# Основная функция обработки поста с фильтром suspended
# -------------------------
async def handle_new_post(message, media=None):
    promo_items = parse_promo_codes(message)
    if not promo_items:
        print("Промокоды не найдены")
        return

    promo_items.sort(key=lambda x: x["nominal"], reverse=True)

    # Фильтруем приостановленных пользователей
    active_chat_ids = [chat_id for chat_id in chat_ids if is_user_active(chat_id)]

    tasks = [asyncio.create_task(account_container(chat_id, promo_items)) for chat_id in active_chat_ids]
    await asyncio.gather(*tasks)

# -------------------------
# Асинхронный HTTP запрос активации промокода
# -------------------------
async def activate_promo(chat_id, code, access_token):
    headers = {
        "Authorization": f"JWT {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru"
    }
    data = {"code": code, "token": "1a"}  # обязательно для API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL_PROMO_ACTIVATE, headers=headers, json=data, timeout=15) as resp:
                return await resp.json()
    except Exception as e:
        return {"status": "error", "info": str(e)}

# -------------------------
# Асинхронный HTTP запрос ставки
# -------------------------
async def make_bet(chat_id, promo, access_token, amount):
    headers = {"Authorization": f"JWT {access_token}"}
    data = {
        "playersCount": 2,
        "isBotPvp": True,
        "amount": amount,
        "userItemIds": []
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL_BET, headers=headers, json=data, timeout=5) as resp:
                return await resp.json()
    except Exception as e:
        return {"status": "error", "info": str(e)}
