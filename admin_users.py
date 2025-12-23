import base64
import json
from datetime import datetime, timedelta

from access_control import generate_key

USERS_PER_PAGE = 5

KEY_DURATION_OPTIONS = [
    ("2 минуты", timedelta(minutes=2)),
    ("1 час", timedelta(hours=1)),
    ("3 часа", timedelta(hours=3)),
    ("6 часов", timedelta(hours=6)),
    ("12 часов", timedelta(hours=12)),
    ("1 день", timedelta(days=1)),
    ("2 дня", timedelta(days=2)),
    ("3 дня", timedelta(days=3)),
    ("7 дней", timedelta(days=7))
]


class AdminUsersAPI:
    def __init__(self, ram_data):
        self.RAM_DATA = ram_data

    # ------------------------
    # Список пользователей с пагинацией
    # ------------------------
    def get_users_page(self, page: int = 0):
        chat_ids = list(self.RAM_DATA.keys())
        total_pages = (len(chat_ids) - 1) // USERS_PER_PAGE + 1

        start = page * USERS_PER_PAGE
        end = start + USERS_PER_PAGE
        page_chat_ids = chat_ids[start:end]

        users = []
        for uid in page_chat_ids:
            user_data = self.RAM_DATA.get(uid, {})
            users.append({
                "chat_id": uid,
                "suspended": user_data.get("suspended", True),
                "subscription_until": user_data.get("subscription_until"),
            })

        return {
            "users": users,
            "page": page,
            "total_pages": total_pages
        }

    # ------------------------
    # Информация о пользователе
    # ------------------------
    def get_user_info(self, uid: int):
        user_data = self.RAM_DATA.get(uid)
        if not user_data:
            return {"error": "User not found"}

        refresh_token = user_data.get("refresh_token")
        user_id = self.extract_user_id_from_refresh(refresh_token) if refresh_token else None

        return {
            "chat_id": uid,
            "suspended": user_data.get("suspended", True),
            "subscription_until": user_data.get("subscription_until"),
            "refresh_token": refresh_token,
            "user_id": user_id
        }

    # ------------------------
    # Получение токенов пользователя
    # ------------------------
    def get_user_tokens(self, uid: int):
        user_data = self.RAM_DATA.get(uid)
        if not user_data:
            return {"error": "User not found"}
        return {
            "access_token": user_data.get("access_token"),
            "refresh_token": user_data.get("refresh_token")
        }

    # ------------------------
    # Приостановка/возобновление пользователя
    # ------------------------
    def toggle_user_suspended(self, uid: int):
        user_data = self.RAM_DATA.get(uid)
        if not user_data:
            return {"error": "User not found"}

        user_data["suspended"] = not user_data.get("suspended", False)
        return {
            "chat_id": uid,
            "suspended": user_data["suspended"]
        }

    # ------------------------
    # Генерация ключа
    # ------------------------
    def generate_key(self, duration_idx: int):
        if duration_idx < 0 or duration_idx >= len(KEY_DURATION_OPTIONS):
            return {"error": "Invalid duration index"}

        label, duration = KEY_DURATION_OPTIONS[duration_idx]
        key = generate_key(duration)
        return {
            "key": key,
            "duration_label": label,
            "expires_at": (datetime.now() + duration).timestamp()
        }

    # ------------------------
    # Вспомогательная функция для user_id из refresh_token
    # ------------------------
    @staticmethod
    def extract_user_id_from_refresh(refresh_token: str):
        try:
            parts = refresh_token.split(".")
            if len(parts) != 3:
                return None
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()))
            return payload.get("id")
        except Exception:
            return None
