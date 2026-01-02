import asyncio
import time
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY
from promo_processor import handle_new_post

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)

CHECK_INTERVAL = 4
MONITOR_DURATION = 5 * 60

POST_CACHE = {}

# 🔥 ТЕСТИМ ТОЛЬКО ОДИН КАНАЛ
@client.on(events.NewMessage(chats=[CHANNEL_ORDINARY]))
async def new_message_handler(event):
    msg = event.message
    chat_id = event.chat_id

    fake_promo = f"0.75$ — POST{msg.id}"

    print("\n=== НОВЫЙ ПОСТ ===")
    print(f"Канал: {chat_id}")
    print(f"Передано в promo_processor: {fake_promo}")
    print("=================\n")

    await handle_new_post(fake_promo, None)

    POST_CACHE[msg.id] = {
        "text": fake_promo,
        "timestamp": time.time()
    }

    asyncio.create_task(track_post_changes(chat_id, msg.id))


async def track_post_changes(chat_id, message_id):
    start_time = time.time()

    while time.time() - start_time < MONITOR_DURATION:
        await asyncio.sleep(CHECK_INTERVAL)

        try:
            msg = await client.get_messages(chat_id, ids=message_id)
            if not msg:
                continue
        except Exception as e:
            print(f"[track_post_changes] Ошибка: {e}")
            continue

        new_fake_promo = f"0.75$ — POST{msg.id}"
        old_fake = POST_CACHE.get(message_id, {}).get("text")

        if new_fake_promo == old_fake:
            continue

        POST_CACHE[message_id]["text"] = new_fake_promo

        print(f"\n[UPDATE] Пост {message_id} изменён")
        print(f"Повторная отправка в promo_processor: {new_fake_promo}\n")

        await handle_new_post(new_fake_promo, None)


async def connection_watcher():
    while True:
        if not client.is_connected():
            print("🔄 Reconnecting...")
            await client.connect()
        await asyncio.sleep(5)