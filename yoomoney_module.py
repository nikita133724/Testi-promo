# yoomoney_module.py
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

CLIENT_ID = "F11DB8BE3A35360A2005C5F1542E842FB12BF7ABC8F78ED9BF2C02AC4C79F2A9"
CLIENT_SECRET = "75344E66298F18E1565721F87032CC4B180389C5A82A710FE7EF249C01E3890F8F40D657BDC51FF05726A7CA15A605777306B43E9E79EC4130A6E76504978F3D"
SUCCESS_REDIRECT_URI = "https://tg-bot-test-gkbp.onrender.com/payment/success"
YOOMONEY_WALLET = "4100117872411525"  

def create_payment_link(chat_id: int, amount: int) -> str:
    comment = f"user_{chat_id}"
    url = (
        f"https://yoomoney.ru/quickpay/confirm.xml"
        f"?receiver={YOOMONEY_WALLET}"
        f"&quickpay-form=shop"
        f"&targets={comment}"
        f"&sum={amount}"
        f"&currency=643"
        f"&successURL={SUCCESS_REDIRECT_URI}"
    )
    return url
async def get_access_token() -> str:
    """Получение access_token через OAuth2 client credentials"""
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        async with session.post("https://yoomoney.ru/oauth/token", data=data) as resp:
            token_data = await resp.json()
            return token_data.get("access_token")

async def send_payment_link(bot, chat_id: int, amount: int):
    """
    Генерация ссылки и отправка пользователю через Telegram
    """
    token = await get_access_token()  # <-- получаем токен
    payment_url = await create_payment_link(chat_id, amount, token)  # <-- передаем токен
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Оплатить подписку", url=payment_url)]])
    await bot.send_message(chat_id, "Нажмите для оплаты:", reply_markup=keyboard)