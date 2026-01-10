from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import json
from datetime import datetime, timedelta, timezone
import hashlib
import urllib.parse
import secrets
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, PlainTextResponse, FileResponse
import time
from telegram_bot import RAM_DATA, _save_to_redis_partial, bot, send_message_to_user, ADMIN_CHAT_ID, app as tg_app
from orders_store import next_order_id, save_order, get_order, ORDERS

router = APIRouter()
REDIRECTS: dict[str, dict] = {}

INSTRUCTION_URL = "https://telegra.ph/Instrukciya-po-ispolzovaniyu-tg-bota-01-06"
YOOMONEY_WALLET = "4100117872411525"
SUCCESS_REDIRECT_URI = "https://t.me/promo_run_bot"
YOOMONEY_NOTIFICATION_SECRET = "7MkJEHOhk+g+z9RRNl4wCqEr"

MSK = timezone(timedelta(hours=3))
SECRET_LABEL_KEY = "superqownsnms18191wnwnw181991wnsnsm199192nwnnsjs292992snnejsjs"

MAX_DIFF_PERCENT = 0.1
MIN_HASH_LEN = 25


def safe_telegram_call(coro):
    tg_app.create_task(coro)

def create_temp_redirect(real_url, ttl=300):
    token = secrets.token_urlsafe(24)
    REDIRECTS[token] = {
        "url": real_url,
        "expires": time.time() + ttl
    }
    return token
    
async def cleanup_redirects():
    while True:
        now = time.time()
        for k in list(REDIRECTS.keys()):
            if REDIRECTS[k]["expires"] < now:
                del REDIRECTS[k]
        await asyncio.sleep(60)
        
def verify_yoomoney_signature(data: dict) -> bool:
    """
    Проверка SHA1 подписи YooMoney по официальной схеме.
    """
    # Составляем список полей в нужном порядке
    # Все поля UTF-8, пустые остаются пустыми, разделитель "&"
    notification_type = data.get("notification_type", "")
    
    # Для card-incoming поле sender всегда пустое
    if notification_type == "card-incoming":
        parts = [
            data.get("notification_type", ""),
            data.get("operation_id", ""),
            data.get("amount", ""),
            data.get("currency", ""),
            data.get("datetime", ""),
            "",  # sender пустой
            data.get("codepro", ""),
            YOOMONEY_NOTIFICATION_SECRET,
            data.get("label", "")
        ]
    else:
        parts = [
            data.get("notification_type", ""),
            data.get("operation_id", ""),
            data.get("amount", ""),
            data.get("currency", ""),
            data.get("datetime", ""),
            data.get("sender", ""),
            data.get("codepro", ""),
            YOOMONEY_NOTIFICATION_SECRET,
            data.get("label", "")
        ]

    # Собираем строку с '&'
    check_string = "&".join(parts)

    local_sha1 = hashlib.sha1(check_string.encode("utf-8")).hexdigest()

    # 🔍 Для отладки
    print("🧾 SIGNATURE DEBUG")
    for i, p in enumerate(parts, 1):
        print(f"{i}: [{p}]")
    print("CHECK STRING:", check_string)
    print("LOCAL SHA1 :", local_sha1)
    print("REMOTE SHA1:", data.get("sha1_hash"))

    return local_sha1 == data.get("sha1_hash")

# ----------------------- LABEL
def make_label(chat_id, order_id, amount):
    plain = f"{chat_id}|{order_id}|{int(amount)}"
    h = hashlib.sha256((plain + SECRET_LABEL_KEY).encode()).hexdigest()
    return f"{plain}|{h}"


# ----------------------- TIMER
async def pending_order_timeout(order_id, timeout=300):
    await asyncio.sleep(timeout)

    order = get_order(order_id)
    if not order:
        return

    if "message_id" in order:
        try:
            safe_telegram_call(bot.delete_message(order["chat_id"], order["message_id"]))
        except:
            pass

    if order["status"] == "pending":
        order["status"] = "expired"
        save_order(order_id, order)
        safe_telegram_call(bot.send_message(order["chat_id"], f"⏳ Время оплаты истекло. Заказ #{order_id}"))


# ----------------------- CREATE PAYMENT
def create_payment_link(chat_id, amount):

    order_id = next_order_id()
    label = make_label(chat_id, order_id, amount)

    targets = urllib.parse.quote_plus(f"promo_run_bot, заказ №{order_id}")

    url = (
        f"https://yoomoney.ru/quickpay/confirm.xml"
        f"?receiver={YOOMONEY_WALLET}"
        f"&quickpay-form=shop"
        f"&targets={targets}"
        f"&sum={amount}"
        f"&currency=643"
        f"&successURL={SUCCESS_REDIRECT_URI}"
        f"&label={label}"
    )

    order = {
        "chat_id": chat_id,
        "amount": amount,
        "currency": "RUB",
        "provider": "yoomoney",
        "status": "pending",
        "created_at": int(datetime.now(timezone.utc).timestamp()),
        "paid_at": None,
        "payment_id": None,
        "processing": False
    }

    save_order(order_id, order)
    asyncio.create_task(pending_order_timeout(order_id))

    return url, order_id


# ----------------------- SEND LINK
async def send_payment_link(bot, chat_id, amount):

    url, order_id = create_payment_link(chat_id, amount)

    text = (
        f"💳 Сумма: {amount}₽\n"
        f"🧾 Заказ: #{order_id}\n"
        f"⏳ Время на оплату: 5 минут"
    )

    token = create_temp_redirect(url)
    public_url = f"https://tg-bot-test-gkbp.onrender.com/p/{token}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить", url=public_url)]])
    msg = await bot.send_message(chat_id, text, reply_markup=keyboard)

    order = get_order(order_id)
    order["message_id"] = msg.message_id
    save_order(order_id, order)


# ----------------------- IPN
async def yoomoney_ipn(operation_id, amount, currency, datetime_str, label, sha1_hash):

    try:
        chat_id, order_id, expected_amount_str, provided_hash = label.split("|")
        order_id = int(order_id)
        expected_amount = float(expected_amount_str)

        plain = f"{chat_id}|{order_id}|{expected_amount_str}"
        expected_hash = hashlib.sha256((plain + SECRET_LABEL_KEY).encode()).hexdigest()

        if len(provided_hash) < MIN_HASH_LEN or not expected_hash.startswith(provided_hash):
            return {"status": "error", "reason": "invalid_label_hash"}

        if amount < expected_amount * (1 - MAX_DIFF_PERCENT):
            return {"status": "error", "reason": "wrong_amount"}

    except:
        return {"status": "error", "reason": "invalid_label"}

    if currency != "643":
        return {"status": "error", "reason": "wrong_currency"}

    order = get_order(order_id)
    if not order or order.get("processing"):
        return {"status": "ok"}

    if order["status"] == "expired":
        print(f"[YOOMONEY IPN] оплата по просроченному заказу {order_id}")
        return {"status": "error", "reason": "order_expired"}
        
    if order["status"] == "paid":
        return {"status": "ok"}

    order["processing"] = True
    save_order(order_id, order)

    try:
        order["status"] = "paid"
        order["paid_at"] = int(datetime.fromisoformat(datetime_str.replace("Z", "+00:00")).timestamp())
        order["payment_id"] = operation_id
        save_order(order_id, order)

        try:
            await bot.delete_message(order["chat_id"], order.get("message_id"))
        except:
            pass

        chat_id = int(chat_id)
        now = datetime.now(timezone.utc).timestamp()
        
        raw_subscription_until = RAM_DATA.get(chat_id, {}).get("subscription_until")
        current_until = float(raw_subscription_until) if isinstance(raw_subscription_until, (int, float)) else 0
        raw_suspended = RAM_DATA.get(chat_id, {}).get("suspended")
        suspended = bool(raw_suspended) if raw_suspended is not None else False
        
        was_active = current_until > now and not suspended
        was_suspended = not was_active
        
        # Продление подписки
        base = max(current_until, now)
        new_until = base + 30 * 24 * 60 * 60
        
        RAM_DATA.setdefault(chat_id, {})
        RAM_DATA[chat_id]["subscription_until"] = new_until
        RAM_DATA[chat_id]["suspended"] = False
        _save_to_redis_partial(chat_id, {"subscription_until": new_until, "suspended": False})
        
        until_text = datetime.fromtimestamp(new_until, tz=MSK).strftime("%d.%m.%Y %H:%M")
        
        if was_suspended:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            from telegram_bot import build_reply_keyboard
            
            inline = InlineKeyboardMarkup([
                [InlineKeyboardButton("📘 Инструкция", url=INSTRUCTION_URL)]
            ])
            
            await send_message_to_user(
                bot,
                chat_id,
                f"✅ Подписка активна до {until_text}. Заказ: #{order_id}",
                reply_markup=inline
            )
            
            # затем отправляем основную клавиатуру отдельно
            await bot.send_message(
                chat_id,
                "Выберите действие:",
                reply_markup=build_reply_keyboard(chat_id)
            )
        else:
            await bot.send_message(chat_id, f"✅ Подписка активна до {until_text}. Заказ: #{order_id}")
        print(f"[YOOMONEY IPN] заказ {order_id} оплачен для  chat {chat_id}, подписка до {until_text}")
        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"💰 Новая покупка подписки\n\n"
                f"Пользователь: {chat_id}\n"
                f"Заказ: #{order_id}\n"
                f"Сумма: {amount}₽\n"
                f"Активна до: {until_text}"
            )
        except Exception as e:
            print(f"[ADMIN NOTIFY ERROR] {e}")

    finally:
        order["processing"] = False
        save_order(order_id, order)

    return {"status": "ok"}


# ----------------------- HISTORY
def get_last_orders(chat_id, count=4):
    orders = [(oid, o) for oid, o in ORDERS.items() if o["chat_id"] == chat_id]
    orders.sort(key=lambda x: x[1]["created_at"], reverse=True)
    return orders[:count]
    
@router.get("/p/{token}")
async def temp_redirect(token: str):
    data = REDIRECTS.get(token)

    if not data:
        # Ссылка вообще не найдена — показываем "потерялся" JPEG
        return FileResponse("static/Миньоны.jpeg", media_type="image/jpeg", status_code=404)

    if time.time() > data["expires"]:
        del REDIRECTS[token]
        # Срок действия истек — тоже картинка
        return FileResponse("static/Миньоны.jpeg", media_type="image/jpeg", status_code=410)

    # Всё ок — редиректим
    return RedirectResponse(data["url"])


@router.post("/yoomoney_ipn")
async def yoomoney_ipn_endpoint(request: Request):
    form = await request.form()
    data = dict(form)

    if not verify_yoomoney_signature(data):
        print("❌ INVALID YOOMONEY SIGNATURE")
        return {"status": "error", "reason": "invalid_signature"}

    try:
        amount_float = float(data["amount"].replace(",", "."))
    except Exception as e:
        print(f"[YOOMONEY IPN] amount error: {e}")
        return {"status": "error", "reason": "invalid_amount"}

    print("✅ YOOMONEY IPN VERIFIED:", data)

    return await yoomoney_ipn(
        operation_id=data["operation_id"],
        amount=amount_float,
        currency=data["currency"],
        datetime_str=data["datetime"],
        label=data["label"],
        sha1_hash=data["sha1_hash"]
    )