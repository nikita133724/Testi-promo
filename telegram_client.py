import asyncio
import time
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY, CHANNEL_SPECIAL]

POST_CACHE = {}  # {chat_id: {message_id: {"text": "...", "timestamp": ...}}}

CHECK_INTERVAL = 4  # проверять каждые 4 секунды
MONITOR_DURATION = 5 * 60  # 5 минут

@client.on(events.NewMessage(chats=channels))
async def new_message_handler(event):
    msg = event.message
    chat_id = event.chat_id
    message_text = msg.message or ""
    media = msg.media

    # Логирование
    media_info = None
    if media:
        if isinstance(media, MessageMediaPhoto):
            media_info = "Фото"
        elif isinstance(media, MessageMediaDocument):
            mime = getattr(media.document, 'mime_type', '')
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
        # Обрабатываем первый раз
        await handle_new_post(message_text, media)

        # Сохраняем текст в кэш
        POST_CACHE.setdefault(chat_id, {})[msg.id] = {
            "text": message_text,
            "timestamp": time.time()
        }

        # Создаем задачу для отслеживания изменений
        asyncio.create_task(track_post_changes(chat_id, msg.id, media))

async def track_post_changes(chat_id, message_id, media=None):
    """
    Проверяет пост каждые CHECK_INTERVAL секунд
    в течение MONITOR_DURATION. Если текст изменился — повторно обрабатывает.
    """
    start_time = time.time()
    while time.time() - start_time < MONITOR_DURATION:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            msg = await client.get_messages(chat_id, ids=message_id)
            if not msg:
                continue
            new_text = msg.message or ""
        except Exception as e:
            print(f"[track_post_changes] Ошибка: {e}")
            continue

        old_text = POST_CACHE.get(chat_id, {}).get(message_id, {}).get("text")
        if old_text is None or new_text == old_text:
            continue  # без изменений

        # Текст изменился — обновляем кэш и повторно обрабатываем
        POST_CACHE[chat_id][message_id]["text"] = new_text
        print(f"[UPDATE] Пост {message_id} изменён, повторная обработка!")
        await handle_new_post(new_text, media)
        
async def connection_watcher():
    while True:
        if not client.is_connected():
            print("🔄 Reconnecting...")
            await client.connect()
        await asyncio.sleep(5)