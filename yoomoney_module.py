# yoomoney_module.py
import aiohttp
import asyncio
from base64 import b64encode
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# -----------------------
# Настройки вашего приложения
# -----------------------
CLIENT_ID = "F11DB8BE3A35360A2005C5F1542E842FB12BF7ABC8F78ED9BF2C02AC4C79F2A9"
CLIENT_SECRET = "75344E66298F18E1565721F87032CC4B180389C5A82A710FE7EF249C01E3890F8F40D657BDC51FF05726A7CA15A605777306B43E9E79EC4130A6E76504978F3D"
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"

# -----------------------
# RAM-хранилище для платежей (тест)
# -----------------------
PAYMENTS_RAM = {}  # payment_id -> {chat_id, amount, status}

# -----------------------
# Генерация уникального номера платежа
# -----------------------
NEXT_PAYMENT_NUMBER = 1
def get_next_payment_number() -> int:
    global NEXT_PAYMENT_NUMBER
    num = NEXT_PAYMENT_NUMBER
    NEXT_PAYMENT_NUMBER += 1
    return num

# -----------------------
# Создание платежа через YooKassa API
# -----------------------
async def create_payment(chat_id: int, amount: int) -> dict:
    payment_number = get_next_payment_number()
    description = f"user_{chat_id}_payment_{payment_number}"

    # Basic Auth заголовок
    auth_str = b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_str}",
        "Content-Type": "application/json"
    }

    payload = {
        "amount": {
            "value": f"{amount:.2f}",  # строка с двумя знаками после запятой
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": SUCCESS_REDIRECT_URI
        },
        "capture": True,
        "description": description
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.yookassa.ru/v3/payments",
            json=payload,
            headers=headers
        ) as resp:
            data = await resp.json()
            payment_id = data.get("id")
            payment_url = data.get("confirmation", {}).get("confirmation_url")

            # сохраняем в RAM
            PAYMENTS_RAM[payment_id] = {
                "chat_id": chat_id,
                "amount": amount,
                "status": "pending",
                "description": description
            }

            return {"payment_id": payment_id, "payment_url": payment_url}

# -----------------------
# Отправка ссылки пользователю
# -----------------------
async def send_payment_link(bot, chat_id: int, amount: int):
    payment = await create_payment(chat_id, amount)
    payment_url = payment.get("payment_url")

    if payment_url:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Оплатить подписку", url=payment_url)]
        ])
        await bot.send_message(chat_id, f"Сумма к оплате: {amount}₽\nНажмите для оплаты:", reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, f"Сумма к оплате: {amount}₽\nСсылка на оплату пока недоступна.")

# -----------------------
# Обработка уведомлений от YooKassa (Webhook)
# -----------------------
async def handle_payment_notification(data: dict, bot):
    """
    data - словарь, который приходит от YooKassa
    bot - объект telegram.Bot
    """
    obj = data.get("object", {})
    payment_id = obj.get("id")
    status = obj.get("status")

    if payment_id not in PAYMENTS_RAM:
        return  # неизвестный платеж

    payment_info = PAYMENTS_RAM[payment_id]
    chat_id = payment_info["chat_id"]

    if status == "succeeded":
        payment_info["status"] = "paid"
        await bot.send_message(
            chat_id,
            f"✅ Оплата подтверждена! Сумма: {payment_info['amount']}₽"
        )
        del PAYMENTS_RAM[payment_id]

    elif status == "canceled":
        payment_info["status"] = "canceled"
        await bot.send_message(
            chat_id,
            f"❌ Оплата отменена. Попробуйте снова."
        )
        del PAYMENTS_RAM[payment_id]