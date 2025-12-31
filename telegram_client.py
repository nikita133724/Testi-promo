from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post
import asyncio
import time
client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY, CHANNEL_SPECIAL]


POST_CACHE = {}

@client.on(events.NewMessage(chats=channels))
async def new_message_handler(event):
    message = event.message
    message_id = message.id
    chat_id = event.chat_id
    message_text = message.message or ""
    media = message.media

    # --- логирование и обработка медиа как раньше ---
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

    # --- Отправляем в promo_processor ---
    if message_text:
        await handle_new_post(message_text, media)

    # --- Сохраняем пост в кэш для отслеживания изменений ---
    POST_CACHE.setdefault(chat_id, {})[message_id] = {
        "text": message_text,
        "timestamp": time.time()
    }

    # --- Запускаем фоновую проверку изменений ---
    asyncio.create_task(track_post_changes(chat_id, message_id, media))
    
async def track_post_changes(chat_id, message_id, media=None):
    """
    Отслеживает изменения текста поста в течение 5 минут.
    Если текст поменялся — заново отправляет в promo_processor.
    """
    CHECK_INTERVAL = 10  # проверять каждые 10 секунд
    TIMEOUT = 5 * 60     # 5 минут

    start_time = time.time()
    while time.time() - start_time < TIMEOUT:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            messages = await client.get_messages(chat_id, ids=message_id)
            if not messages:
                continue
            message = messages[0]
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
            await handle_new_post(new_text, media)
            
