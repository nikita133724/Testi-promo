from fastapi import FastAPI, Request
import asyncio
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN
from yoomoney_module import handle_payment_notification

app = FastAPI()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

@app.post("/yoomoney_webhook")
async def yoomoney_webhook(request: Request):
    """
    Endpoint для уведомлений от YooMoney
    """
    data = await request.json()
    
    # Обрабатываем уведомление в отдельном таске (не блокируем FastAPI)
    asyncio.create_task(handle_payment_notification(data, bot))
    
    # YooMoney ожидает HTTP 200
    return {"status": "ok"}