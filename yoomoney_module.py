# yoomoney_module.py
import aiohttp
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# -----------------------
# Настройки вашего приложения
# -----------------------
CLIENT_ID = "F11DB8BE3A35360A2005C5F1542E842FB12BF7ABC8F78ED9BF2C02AC4C79F2A9"
CLIENT_SECRET = "75344E66298F18E1565721F87032CC4B180389C5A82A710FE7EF249C01E3890F8F40D657BDC51FF05726A7CA15A605777306B43E9E79EC4130A6E76504978F3D"
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"
YOOMONEY_WALLET = "4100117872411525"

# -----------------------
# RAM-хранилище для платежей (тест)
# -----------------------
PAYMENTS_RAM = {}  # payment_id -> {chat_id, amount, status}

# -----------------------
# Получение токена Human API
# -----------------------
async def get_access_token() -> str:
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        async with session.post("https://yoomoney.ru/oauth/token", data=data) as resp:
            token_data = await resp.json()
            return token_data.get("access_token")

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
# Создание платежа через API
# -----------------------
async def create_payment(chat_id: int, amount: int) -> dict:
    access_token = await get_access_token()
    payment_number = get_next_payment_number()
    comment = f"user_{chat_id}_payment_{payment_number}"

    payload = {
        "amount": str(amount),
        "currency": "RUB",
        "comment": comment,
        "receiver": YOOMONEY_WALLET,
        "success_redirect_uri": SUCCESS_REDIRECT_URI
    }

    headers = {"Authorization": f"Bearer {access_token}"}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://yoomoney.ru/api/payments/create",
            json=payload,
            headers=headers
        ) as resp:
            data = await resp.json()
            payment_id = data.get("payment_id")
            payment_url = data.get("confirmation_url") or data.get("confirmation", {}).get("confirmation_url")
            # сохраняем в RAM
            PAYMENTS_RAM[payment_id] = {
                "chat_id": chat_id,
                "amount": amount,
                "status": "pending",
                "comment": comment
            }
            return {"payment_id": payment_id, "payment_url": payment_url}

# -----------------------
# Отправка ссылки пользователю
# -----------------------
async def send_payment_link(bot, chat_id: int, amount: int):
    payment = await create_payment(chat_id, amount)
    payment_url = payment["payment_url"]

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Оплатить подписку", url=payment_url)]
    ])
    await bot.send_message(chat_id, f"Сумма к оплате: {amount}₽\nНажмите для оплаты:", reply_markup=keyboard)

# -----------------------
# Обработка уведомлений от YooMoney (Webhook)
# -----------------------
async def handle_payment_notification(data: dict, bot):
    """
    data - словарь, который приходит от YooMoney
    bot - объект telegram.Bot
    """
    payment_id = data.get("object", {}).get("id")
    status = data.get("object", {}).get("status")

    if payment_id not in PAYMENTS_RAM:
        return  # неизвестный платеж

    payment_info = PAYMENTS_RAM[payment_id]
    chat_id = payment_info["chat_id"]

    if status == "succeeded":
        # обновляем статус
        payment_info["status"] = "paid"
        # уведомляем пользователя
        await bot.send_message(chat_id, f"✅ Оплата подтверждена! Сумма: {payment_info['amount']}₽")
        # удаляем данные из RAM (тест)
        del PAYMENTS_RAM[payment_id]

    elif status == "canceled":
        payment_info["status"] = "canceled"
        await bot.send_message(chat_id, f"❌ Оплата отменена. Попробуйте снова.")
        del PAYMENTS_RAM[payment_id]