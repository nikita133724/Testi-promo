from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageEntitySpoiler, MessageEntityCode, MessageEntityPre
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post
import asyncio
import time

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY, CHANNEL_SPECIAL]
SPECIAL_USERNAME = CHANNEL_SPECIAL.lstrip("@").lower()

POST_CACHE = {}

def extract_special_promos(message):
    if not message.entities:
        return []

    full_text = message.raw_text or message.message or ""
    results = []

    for ent in message.entities:
        if isinstance(ent, (MessageEntitySpoiler, MessageEntityCode, MessageEntityPre)):
            start = ent.offset
            end = ent.offset + ent.length
            code = full_text[start:end].strip()
            if 4 <= len(code) <= 32:
                results.append(code)

    return results

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

    media_info = None
    if media:
        if isinstance(media, MessageMediaPhoto):
            media_info = "Фото"
        elif isinstance(media, MessageMediaDocument):
            mime = getattr(media.document, "mime_type", "")
            if mime.startswith("image/webp"):
                media_info = "Стикер"
            elif mime.startswith("video/"):
                media_info = "Видео"
            else:
                media_info = f"Файл ({mime})"
        else:
            media_info = "Другое медиа"

    print("=== Новый пост ===")
    print(f"Канал/Чат: {chat_id}")
    if message_text and media_info:
        print(f"Текст с медиа ({media_info}): {message_text}")
    elif message_text:
        print(f"Только текст: {message_text}")
    elif media_info:
        print(f"Только медиа: {media_info}")
    else:
        print("Пустое сообщение")
    print("----")

    if message_text:
        if is_special_channel:
            codes = extract_special_promos(message)

            if codes:
                for code in codes:
                    fake_line = f"0.25$ — {code}"
                    print(f"[SPECIAL] Найден промо: {code}")
                    await handle_new_post(fake_line, media)
            else:
                print("[SPECIAL] В посте нет промокодов")
        else:
            await handle_new_post(message_text, media)

    POST_CACHE.setdefault(chat_id, {})[message_id] = {
        "text": message_text,
        "timestamp": time.time()
    }

    asyncio.create_task(track_post_changes(chat_id, message_id, media, is_special_channel))

async def track_post_changes(chat_id, message_id, media=None, is_special_channel=False):
    print(f"[track_post_changes] Старт отслеживания поста {message_id} в чате {chat_id}")

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
            print(f"[track_post_changes] Ошибка при получении сообщения: {e}")
            continue

        old_text = POST_CACHE.get(chat_id, {}).get(message_id, {}).get("text")
        if old_text is None:
            continue

        if new_text != old_text:
            print(f"[UPDATE] Пост {message_id} изменён! Отправляем заново.")
            POST_CACHE[chat_id][message_id]["text"] = new_text

            if is_special_channel:
                codes = extract_special_promos(message)
                if codes:
                    for code in codes:
                        fake_line = f"0.25$ — {code}"
                        print(f"[SPECIAL UPDATE] Найден промо: {code}")
                        await handle_new_post(fake_line, media)
            else:
                await handle_new_post(new_text, media)