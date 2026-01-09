import asyncio
from datetime import datetime, timezone, timedelta
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram_bot import bot, RAM_DATA, _save_to_redis_partial, send_message_to_user, ADMIN_CHAT_ID
from orders_store import next_order_id, save_order, get_order, find_order_by_invoice
from fastapi import APIRouter, Request

router = APIRouter()
INSTRUCTION_URL = "https://telegra.ph/Instrukciya-po-ispolzovaniyu-tg-bota-01-06"
NOWPAYMENTS_API_KEY = "8HFD9KZ-ST94FV1-J32B132-WBJ0S9N"
NOWPAYMENTS_API_URL = "https://api.nowpayments.io/v1/invoice"
MSK = timezone(timedelta(hours=3))

import hmac
import hashlib
import json

async def verify_nowpayments_signature(request: Request, ipn_secret: str) -> bool:
    """
    Проверяет HMAC SHA512 подпись от NowPayments.
    """
    body_bytes = await request.body()  # сырое тело запроса
    signature = request.headers.get("x-nowpayments-sig")
    if not signature:
        return False

    # JSON нужно сериализовать с сортировкой ключей
    body_dict = json.loads(body_bytes.decode())
    sorted_body = json.dumps(body_dict, separators=(",", ":"), sort_keys=True)

    # Вычисляем HMAC SHA512
    hmac_calculated = hmac.new(
        ipn_secret.encode("utf-8"),
        sorted_body.encode("utf-8"),
        hashlib.sha512
    ).hexdigest()

    # Сравниваем безопасно
    return hmac.compare_digest(hmac_calculated, signature)
    
async def rub_to_crypto(amount_rub: float, crypto_currency: str) -> tuple[float, float]:
    # получаем курс USD
    async with aiohttp.ClientSession() as session:
        async with session.get("https://open.er-api.com/v6/latest/RUB") as resp:
            data = await resp.json()

    rate = float(data["rates"]["USD"])
    usd_amount = round(amount_rub * rate, 2)

    # получаем количество крипты
    url = f"https://api.nowpayments.io/v1/estimate?amount={usd_amount}&currency_from=usd&currency_to={crypto_currency}"
    headers = {"x-api-key": NOWPAYMENTS_API_KEY}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            est = await resp.json()

    crypto_amount = float(est["estimated_amount"])
    return usd_amount, crypto_amount
    
# ----------------------- CREATE INVOICE
async def create_invoice(chat_id, amount_rub, currency="USDT", network=None):

    local_order_id = next_order_id()

    callback_url = "https://tg-bot-test-gkbp.onrender.com/payment/nowpayments/ipn"
    description = f"Подписка 30 дней, заказ #{local_order_id}"

    if currency == "USDT":
        crypto_currency = f"usdt{network}"
    else:
        crypto_currency = currency.lower()

    usd_amount, crypto_amount = await rub_to_crypto(amount_rub, crypto_currency)

    payload = {
        "price_amount": usd_amount,
        "price_currency": "usd",
        "pay_currency": crypto_currency,
        "order_description": description,
        "ipn_callback_url": callback_url
    }

    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(NOWPAYMENTS_API_URL, headers=headers, json=payload) as resp:
            data = await resp.json()

    if "invoice_url" not in data:
        raise Exception(f"NOWPayments error: {data}")

    order = {
        "chat_id": chat_id,
        "amount": float(amount_rub),
        "pay_amount": crypto_amount,
        "pay_currency": crypto_currency,
        "status": "pending",
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "invoice_id": str(data["id"]),
        "payment_id": None,
        "provider": "crypto",
        "processing": False,
    }

    save_order(local_order_id, order)
    asyncio.create_task(pending_order_timeout(local_order_id))

    return data["invoice_url"], local_order_id, crypto_amount, crypto_currency
# ----------------------- SEND PAYMENT LINK
async def send_payment_link(bot, chat_id, amount, currency="USDT", network=None):
    url, order_id, pay_amount, pay_currency = await create_invoice(chat_id, amount, currency, network)

    network_text = f" {network.upper()}" if network else ""

    # округляем сумму
    if pay_currency.lower() == "usdttrc":  # USDT TRC20
        display_amount = round(pay_amount, 6)  # до 6 знаков после запятой
    else:  # TRX, TON
        display_amount = round(pay_amount, 3)  # до 3 знаков после запятой

    text = (
        f"💳 Оплата: {display_amount} {pay_currency}\n"
        f"🧾 Заказ: #{order_id}\n"
        f"⏳ Время на оплату: 20 минут"
    )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить", url=url)]])
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)

    order = get_order(order_id)
    order["message_id"] = msg.message_id
    save_order(order_id, order)


# ----------------------- PENDING TIMEOUT
async def pending_order_timeout(order_id, timeout=1200):

    await asyncio.sleep(timeout)

    order = get_order(order_id)
    if not order or order["status"] != "pending":
        return

    try:
        await bot.delete_message(order["chat_id"], order["message_id"])
    except:
        pass

    order["status"] = "expired"
    save_order(order_id, order)

    await bot.send_message(order["chat_id"], f"⏳ Время оплаты истекло. Заказ #{order_id}")


# ----------------------- IPN ENDPOINT
NOWPAYMENTS_IPN_SECRET = "r1W2RgyK3klYcumcW8RfRs5ygb2mkroz"

@router.post("/payment/nowpayments/ipn")
async def nowpayments_ipn_endpoint(request: Request):
    body = await request.body()

    try:
        data = json.loads(body.decode())
    except:
        return {"status": "ok"}

    # Проверяем подпись ТОЛЬКО если платёж финальный
    if data.get("payment_status") == "finished":
        if not await verify_nowpayments_signature(request, NOWPAYMENTS_IPN_SECRET):
            print("⚠️ INVALID SIGNATURE FOR FINISHED PAYMENT")
            return {"status": "error", "reason": "invalid_signature"}

    return await nowpayments_ipn(data)

# ----------------------- ОБРАБОТКА IPN
async def nowpayments_ipn(ipn_data: dict):
    """
    Обработка IPN уведомлений от NowPayments.
    """
    print("NOWPayments IPN:", ipn_data)

    invoice_id = str(ipn_data.get("invoice_id"))
    status = ipn_data.get("payment_status")
    actually_paid = float(ipn_data.get("actually_paid", 0))  # реально получено

    if not invoice_id:
        return {"status": "error", "reason": "missing_invoice_id"}

    # Если оплата ещё не завершена, просто ждём
    if status != "finished":
        return {"status": "ok"}

    # Находим локальный заказ по invoice_id
    local_order_id, order = find_order_by_invoice(invoice_id)
    if not order:
        print("Order not found for invoice:", invoice_id)
        return {"status": "ok"}

    chat_id = int(order["chat_id"])
    order_amount = order["amount"]

    # Если заказ уже оплачен или в обработке — ничего не делаем
    if order.get("status") == "paid" or order.get("processing"):
        return {"status": "ok"}

    # Если заказ просрочен — не принимаем платёж
    if order.get("status") == "expired":
        print(f"Платёж по просроченному заказу #{local_order_id}")
        return {"status": "ok"}

    # Проверяем валюту и сумму
    if actually_paid < order["pay_amount"] * 0.995 or ipn_data.get("pay_currency", "").lower() != order["pay_currency"].lower():
        print(f"Не хватает суммы или неверная валюта: {actually_paid} {ipn_data.get('pay_currency')} vs {order['pay_amount']} {order['pay_currency']}")
        return {"status": "ok"}

    # Отмечаем, что заказ в обработке
    order["processing"] = True
    save_order(local_order_id, order)

    try:
        # Помечаем заказ как оплаченный
        order["status"] = "paid"
        save_order(local_order_id, order)

        # Удаляем сообщение с ссылкой на оплату
        try:
            await bot.delete_message(chat_id, order.get("message_id"))
        except:
            pass

        # Продление подписки
        now = datetime.now(timezone.utc).timestamp()
        raw_subscription_until = RAM_DATA.get(chat_id, {}).get("subscription_until")
        current_until = float(raw_subscription_until) if isinstance(raw_subscription_until, (int, float)) else 0
        raw_suspended = RAM_DATA.get(chat_id, {}).get("suspended")
        suspended = bool(raw_suspended) if raw_suspended is not None else False

        was_active = current_until > now and not suspended
        was_suspended = not was_active

        base = max(current_until, now)
        new_until = base + 30 * 24 * 60 * 60

        RAM_DATA.setdefault(chat_id, {})
        RAM_DATA[chat_id]["subscription_until"] = new_until
        RAM_DATA[chat_id]["suspended"] = False
        _save_to_redis_partial(chat_id, {"subscription_until": new_until, "suspended": False})

        until_text = datetime.fromtimestamp(new_until, tz=MSK).strftime("%d.%m.%Y %H:%M")

        # Сообщение пользователю
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from telegram_bot import build_reply_keyboard, send_message_to_user

        if was_suspended:
            inline = InlineKeyboardMarkup([[InlineKeyboardButton("📘 Инструкция", url=INSTRUCTION_URL)]])
            await send_message_to_user(
                bot,
                chat_id,
                f"✅ Подписка активна до {until_text}. Заказ: #{local_order_id}",
                reply_markup=inline
            )
            await bot.send_message(chat_id, "Выберите действие:", reply_markup=build_reply_keyboard(chat_id))
        else:
            await bot.send_message(chat_id, f"✅ Подписка активна до {until_text}. Заказ: #{local_order_id}")

        # Логирование
        print(f"[NOWPayments IPN] заказ {local_order_id} оплачен для chat {chat_id}, подписка до {until_text}")

        # Уведомление админа
        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"💰 Новая покупка подписки\n\nПользователь: {chat_id}\nЗаказ: #{local_order_id}\nСумма: {order_amount}₽\nАктивна до: {until_text}"
            )
        except Exception as e:
            print(f"[ADMIN NOTIFY ERROR] {e}")

    finally:
        # Сохраняем payment_id и снимаем флаг обработки
        order["payment_id"] = ipn_data.get("payment_id")
        order["processing"] = False
        save_order(local_order_id, order)

    return {"status": "ok"}