import asyncio
import time
from telethon import TelegramClient
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)

CHECK_INTERVAL = 0.25  # проверка каждые 250 мс
POST_CACHE = {}

async def fast_tail_monitor(channel):
    last_id = 0

    while True:
        try:
            msgs = await client.get_messages(channel, limit=1)
            if msgs:
                msg = msgs[0]

                if msg.id > last_id:
                    last_id = msg.id

                    # Формируем сообщение для "избранного"
                    text = f"Вышел новый пост {msg.id}"

                    # Отправляем в Saved Messages (me)
                    await client.send_message('me', text)

                    # Сохраняем ID, чтобы не дублировать
                    POST_CACHE[msg.id] = {
                        "timestamp": time.time()
                    }

        except Exception as e:
            print(f"[fast_tail_monitor] Ошибка: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


async def connection_watcher():
    while True:
        if not client.is_connected():
            print("🔄 Reconnecting...")
            await client.connect()
        await asyncio.sleep(5)