from telethon import TelegramClient, events
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument,
    MessageEntitySpoiler, MessageEntityCode, MessageEntityPre
)
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post
import asyncio
import time

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY, CHANNEL_SPECIAL]
SPECIAL_USERNAME = CHANNEL_SPECIAL.lstrip("@").lower()
POST_CACHE = {}

# -----------------------------
# Вспомогательная функция: достаем промо-коды из сообщения
def extract_special_promos(message):
    if not message.entities:
        return []
    results = []
    full_text = message.raw_text or message.message or ""
    for ent in message.entities:
        if isinstance(ent, (MessageEntitySpoiler, MessageEntityCode, MessageEntityPre)):
            start = ent.offset
            end = ent.offset + ent.length
            code = full_text[start:end].strip()
            if 4 <= len(code) <= 32:
                results.append(code)
    return results

# -----------------------------
# Основная функция обработки всех сообщений
@client.on(events.NewMessage(chats=channels))
async def new_message_handler(event):
    message = event.message
    message_id = message.id
    chat_id = event.chat_id
    chat = await event.get_chat()
    chat_username = (getattr(chat, "username", None) or "").lower()
    is_special_channel = chat_username == SPECIAL_USERNAME
    message_text = message.message or ""
    media = message.media

    # -----------------------------
    # Логирование
    print(f"=== Новый пост: chat_id={chat_id} ===")
    if message_text:
        print(f"Текст: {message_text}")
    if media:
        print("Есть медиа")
    print("----")

    # -----------------------------
    # Тестовый режим: спец-канал → пишем в Избранное
    if is_special_channel and message_text:
        try:
            await client.send_message("me", f"[EVENTS] {message_text}")
        except Exception as e:
            print(f"Ошибка отправки в избранное: {e}")

    # -----------------------------
    # Основная обработка промо
    if message_text:
        if is_special_channel:
            codes = extract_special_promos(message)
            if codes:
                for code in codes:
                    fake_line = f"0.25$ — {code}"
                    await handle_new_post(fake_line, media)
        else:
            await handle_new_post(message_text, media)

    # -----------------------------
    # Кэширование поста
    POST_CACHE.setdefault(chat_id, {})[message_id] = {
        "text": message_text,
        "timestamp": time.time()
    }

    # -----------------------------
    # Отслеживание изменений поста
    asyncio.create_task(track_post_changes(chat_id, message_id, media, is_special_channel))

# -----------------------------
# Функция отслеживания изменений поста
async def track_post_changes(chat_id, message_id, media=None, is_special_channel=False):
    CHECK_INTERVAL = 4
    TIMEOUT = 5 * 60
    start_time = time.time()
    while time.time() - start_time < TIMEOUT:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            message = await client.get_messages(chat_id, ids=message_id)
            if not message:
                continue
            new_text = message.message or ""
        except Exception as e:
            print(f"[track_post_changes] Ошибка: {e}")
            continue

        old_text = POST_CACHE.get(chat_id, {}).get(message_id, {}).get("text")
        if old_text is None:
            continue

        if new_text != old_text:
            POST_CACHE[chat_id][message_id]["text"] = new_text
            print(f"[UPDATE] Пост {message_id} изменён!")

            if is_special_channel and new_text:
                try:
                    await client.send_message("me", f"[EVENTS UPDATE] {new_text}")
                except Exception as e:
                    print(f"Ошибка отправки обновленного поста в избранное: {e}")

            # Основная обработка изменений
            if is_special_channel:
                codes = extract_special_promos(message)
                if codes:
                    for code in codes:
                        fake_line = f"0.25$ — {code}"
                        await handle_new_post(fake_line, media)
            else:
                await handle_new_post(new_text, media)

# -----------------------------
# Fallback polling для спец-канала
async def poll_special_channel():
    print("[POLL] Запущен fallback polling спец-канала")
    last_id = 0
    while True:
        try:
            messages = await client.get_messages(CHANNEL_SPECIAL, limit=1)
            if messages:
                msg = messages[0]
                if msg.id != last_id:
                    last_id = msg.id
                    print("[POLL] Новый пост в спец-канале")
                    if msg.message:
                        # Тестовый режим: пишем в Избранное
                        try:
                            await client.send_message("me", f"[POLLING] {msg.message}")
                        except Exception as e:
                            print(f"Ошибка отправки в избранное: {e}")

                    codes = extract_special_promos(msg)
                    if codes:
                        for code in codes:
                            fake_line = f"0.25$ — {code}"
                            await handle_new_post(fake_line, msg.media)
        except Exception as e:
            print(f"[POLL] Ошибка: {e}")

        await asyncio.sleep(0.3)

