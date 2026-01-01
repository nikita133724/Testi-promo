from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from config import TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNEL_ORDINARY, CHANNEL_SPECIAL
from promo_processor import handle_new_post

client = TelegramClient(TELEGRAM_SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)
channels = [CHANNEL_ORDINARY, CHANNEL_SPECIAL]

@client.on(events.NewMessage(chats=channels))
async def new_message_handler(event):
    message_text = event.message.message or ""
    media = event.message.media

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

    # Логирование
    print("=== Новый пост ===")
    print(f"Канал/Чат: {event.chat_id}")
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
        
        await handle_new_post(message_text, media)
        
async def connection_watcher():
    while True:
        if not client.is_connected():
            print("🔄 Reconnecting...")
            await client.connect()
        await asyncio.sleep(5)