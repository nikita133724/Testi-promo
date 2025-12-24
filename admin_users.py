import base64
import json
import aiohttp
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import ContextTypes

USERS_PER_PAGE = 5

from access_control import generate_key
from datetime import timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

KEY_DURATION_OPTIONS = [
    ("1 час", timedelta(hours=1)),
    ("2 минуты", timedelta(minutes=2)),
    ("3 часа", timedelta(hours=3)),
    ("6 часов", timedelta(hours=6)),
    ("12 часов", timedelta(hours=12)),
    ("1 день", timedelta(days=1)),
    ("2 дня", timedelta(days=2)),
    ("3 дня", timedelta(days=3)),
    ("7 дней", timedelta(days=7))
]

# ----------------------
# Вспомогательные функции
def extract_user_id_from_refresh(refresh_token: str):
    """Извлекает user_id из JWT refresh token"""
    try:
        parts = refresh_token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()))
        return payload.get("id")
    except Exception:
        return None

async def fetch_site_nickname(user_id: int):
    """Получает никнейм пользователя с сайта cs2run.app"""
    url = f"https://cs2run.app/profile/{user_id}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("data", {}).get("name")
    except Exception:
        return None

# ----------------------
# Основной класс
class AdminUsers:
    def __init__(self, ram_data, bot):
        self.RAM_DATA = ram_data
        self.bot = bot
        self.user_pages = {}      # chat_id администратора -> текущая страница
        self.admin_state = {}     # chat_id админа -> состояние уведомлений

    # -----------------------
    # Список пользователей
    async def show_users(self, admin_chat_id, query=None):
        self.user_pages[admin_chat_id] = 0
        await self._send_user_page(admin_chat_id, query)

    # -----------------------
    # Пагинация
    async def paginate(self, admin_chat_id, direction, query=None):
        page = self.user_pages.get(admin_chat_id, 0)
        chat_ids = list(self.RAM_DATA.keys())
        total_pages = (len(chat_ids) - 1) // USERS_PER_PAGE + 1

        if direction == "next" and page + 1 < total_pages:
            page += 1
        elif direction == "back" and page > 0:
            page -= 1

        self.user_pages[admin_chat_id] = page
        await self._send_user_page(admin_chat_id, query)

    # -----------------------
    # Отрисовка страницы пользователей
    async def _send_user_page(self, admin_chat_id, query=None):
        chat_ids = list(self.RAM_DATA.keys())
        page = self.user_pages.get(admin_chat_id, 0)

        start = page * USERS_PER_PAGE
        end = start + USERS_PER_PAGE
        page_chat_ids = chat_ids[start:end]

        buttons = []
        for uid in page_chat_ids:
            try:
                user = await self.bot.get_chat(uid)
                username = f"@{user.username}" if user.username else str(uid)
            except Exception:
                username = str(uid)
            buttons.append([InlineKeyboardButton(username, callback_data=f"user_{uid}")])

        # Навигация
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Назад", callback_data="users_back"))
        if end < len(chat_ids):
            nav.append(InlineKeyboardButton("➡️ Вперёд", callback_data="users_next"))
        if nav:
            buttons.append(nav)

        # Уведомления
        buttons.append([
            InlineKeyboardButton("📣 Увед всем", callback_data="notify_all"),
            InlineKeyboardButton("📩 Увед юзеру", callback_data="notify_user")
        ])

        # Кнопка выхода
        buttons.append([InlineKeyboardButton("❌ Выход", callback_data="users_exit")])

        text = f"Список пользователей (страница {page + 1}/{(len(chat_ids)-1)//USERS_PER_PAGE + 1})"
        markup = InlineKeyboardMarkup(buttons)

        if query:
            await query.message.edit_text(text, reply_markup=markup)
        else:
            await self.bot.send_message(admin_chat_id, text, reply_markup=markup)

    # -----------------------
    # Информация о пользователе + профиль
    async def show_user_info(self, admin_chat_id, uid, query=None):
        user_data = self.RAM_DATA.get(uid, {})

        # Получаем username
        try:
            user = await self.bot.get_chat(uid)
            username = f"@{user.username}" if user.username else str(uid)
        except Exception:
            username = str(uid)

        next_refresh = user_data.get("next_refresh_time", "не задано")

        # ---------- профиль рана ----------
        refresh_token = user_data.get("refresh_token")
        site_name = "Неизвестно"
        profile_html = "Профиль рана"
        profile_link = "#"

        if refresh_token:
            user_id = extract_user_id_from_refresh(refresh_token)
            if user_id:
                nickname = await fetch_site_nickname(user_id)
                if nickname:
                    site_name = nickname
                profile_link = f"https://csgoyz.run/profile/{user_id}"
                profile_html = f'<a href="{profile_link}">Профиль рана</a>'

        # ---------- текст сообщения ----------
        status = "приостановлен" if user_data.get("suspended") else "активен"
        text = (
            f"Информация о пользователе\n\n"
            f"{username}\n"
            f"(chat_id: {uid})\n\n"
            f"Следующий refresh: {next_refresh}\n\n"
            f"{site_name}\n"
            f"{profile_html}\n\n"
            f"Статус: {status}"
        )

        button_text = "🔄 Восстановить" if user_data.get("suspended") else "⏸ Приостановить"
        buttons = [
            [InlineKeyboardButton("🔐 Токены", callback_data=f"user_tokens_{uid}")],
            [InlineKeyboardButton(button_text, callback_data=f"user_pause_{uid}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="settings_users")]
        ]

        markup = InlineKeyboardMarkup(buttons)

        if query:
            await query.message.edit_text(
                text,
                reply_markup=markup,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            await self.bot.send_message(
                admin_chat_id,
                text,
                reply_markup=markup,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

    # -----------------------
    # Токены пользователя
    async def show_tokens(self, admin_chat_id, uid, query=None):
        user_data = self.RAM_DATA.get(uid, {})

        text = (
            f"Токены пользователя {uid}\n\n"
            f"Access Token:\n{user_data.get('access_token','не задан')}\n\n"
            f"Refresh Token:\n{user_data.get('refresh_token','не задан')}"
        )

        buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"user_{uid}")]]
        markup = InlineKeyboardMarkup(buttons)

        if query:
            await query.message.edit_text(text, reply_markup=markup)
        else:
            await self.bot.send_message(admin_chat_id, text, reply_markup=markup)

    # -----------------------
    # Приостановка/восстановление пользователя
    async def pause_user(self, admin_chat_id, uid, query=None):
        user_data = self.RAM_DATA.get(uid)
        if not user_data:
            return
    
        # Переключаем статус
        user_data["suspended"] = not user_data.get("suspended", False)
    
        # Сохраняем в Redis
        from telegram_bot import _save_to_redis_partial
        _save_to_redis_partial(uid, {"suspended": user_data["suspended"]})
    
        # Текст и кнопка
        status_text = "приостановлен" if user_data["suspended"] else "активен"
        button_text = "🔄 Восстановить" if user_data["suspended"] else "⏸ Приостановить"
    
        text = f"Пользователь {uid} теперь {status_text}."
        buttons = [
            [InlineKeyboardButton("🔐 Токены", callback_data=f"user_tokens_{uid}")],
            [InlineKeyboardButton(button_text, callback_data=f"user_pause_{uid}")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="settings_users")]
        ]
        markup = InlineKeyboardMarkup(buttons)
    
        if query:
            await query.message.edit_text(text, reply_markup=markup)
        else:
            await self.bot.send_message(admin_chat_id, text, reply_markup=markup)

    # -----------------------
    # Обработка callback кнопок уведомлений
    async def handle_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()  # убирает "крутилку"
        data = query.data
        admin_id = query.from_user.id

        # ---------- Уведомление всем ----------
        if data == "notify_all":
            msg = await query.message.edit_text(
                "📣 Напишите сообщение для всех пользователей:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Отмена", callback_data="notify_cancel")]]
                )
            )
            self.admin_state[admin_id] = {"mode": "all", "message_id": msg.message_id}

        # ---------- Уведомление одному ----------
        elif data == "notify_user":
            msg = await query.message.edit_text(
                "📩 Введите chat_id или @username пользователя:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Отмена", callback_data="notify_cancel")]]
                )
            )
            self.admin_state[admin_id] = {"mode": "user", "target_uid": None, "message_id": msg.message_id}

        # ---------- Отмена уведомления ----------
        elif data == "notify_cancel":
            state = self.admin_state.get(admin_id)
            if state and "message_id" in state:
                try:
                    await query.message.delete()
                except:
                    pass
                del self.admin_state[admin_id]

    # -----------------------
    # Обработка текста от админа
    async def handle_admin_message(self, message) -> bool:
        admin_id = message.from_user.id
        state = self.admin_state.get(admin_id)

        if not state:
            return False

        if state["mode"] == "all":
            text = message.text
            for uid in self.RAM_DATA.keys():
                try:
                    await self.bot.send_message(uid, text)
                except:
                    pass

            await message.reply_text("✅ Сообщение отправлено всем пользователям")
            del self.admin_state[admin_id]
            return True

        elif state["mode"] == "user":
            if state["target_uid"] is None:
                input_text = message.text.strip()
                target_uid = None

                for uid in self.RAM_DATA.keys():
                    try:
                        chat = await self.bot.get_chat(uid)
                        if (
                            str(uid) == input_text or
                            (chat.username and f"@{chat.username}" == input_text)
                        ):
                            target_uid = uid
                            break
                    except:
                        continue

                if target_uid:
                    self.admin_state[admin_id]["target_uid"] = target_uid
                    await message.reply_text(
                        f"👤 Пользователь найден: {target_uid}\n"
                        f"Теперь введите сообщение:"
                    )
                else:
                    # ❌ Пользователь не найден — сбрасываем ожидание
                    if "message_id" in state:
                        try:
                            # удаляем сообщение с вводом, если нужно
                            await self.bot.delete_message(admin_id, state["message_id"])
                        except:
                            pass
                
                    del self.admin_state[admin_id]  # полностью сбрасываем состояние
                    await message.reply_text(
                        "❌ Пользователь не найден, действие отменено",
                        reply_markup=None  # можно добавить клавиатуру, если нужно
                    )

                return True

            else:
                target_uid = state["target_uid"]
                try:
                    await self.bot.send_message(target_uid, message.text)
                    await message.reply_text(
                        f"✅ Сообщение отправлено пользователю {target_uid}"
                    )
                except:
                    await message.reply_text("❌ Не удалось отправить сообщение")

                del self.admin_state[admin_id]
                return True
    async def open_key_generation_menu(self, admin_chat_id, query=None):
        keyboard = [[InlineKeyboardButton(label, callback_data=f"keygen_{i}")] 
                    for i, (label, _) in enumerate(KEY_DURATION_OPTIONS)]
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="keygen_cancel")])
        markup = InlineKeyboardMarkup(keyboard)
    
        if query:
            await query.message.edit_text("Выберите срок действия ключа:", reply_markup=markup)
        else:
            await self.bot.send_message(admin_chat_id, "Выберите срок действия ключа:", reply_markup=markup)
    
    async def handle_keygen_callback(self, admin_chat_id, data, query=None):
        if data == "keygen_cancel":
            if query:
                await query.message.delete()
            return
    
        if data.startswith("keygen_"):
            idx = int(data.split("_")[1])
            label, duration = KEY_DURATION_OPTIONS[idx]
            key = generate_key(duration)  # используем существующую функцию из access_control
            text = f"✅ Новый ключ на {label}:\n`{key}`"
            if query:
                await query.message.edit_text(text, parse_mode="Markdown")
            else:
                await self.bot.send_message(admin_chat_id, text, parse_mode="Markdown")
    async def get_username(self, uid: int) -> str:
        """
        Получает username Telegram-пользователя.
        Если username нет, возвращает chat_id как строку.
        """
        try:
            user = await self.bot.get_chat(uid)
            return f"@{user.username}" if user.username else str(uid)
        except Exception:
            return str(uid)
