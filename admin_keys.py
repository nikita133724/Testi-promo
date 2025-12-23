from datetime import datetime, timedelta
from access_control import ACCESS_KEYS, generate_key, KEY_DURATION_OPTIONS

class AdminKeysAPI:
    def __init__(self):
        pass

    # ------------------------
    # Просмотр всех активных ключей
    # ------------------------
    def list_keys(self):
        keys_list = []
        now = datetime.now()
        for key, info in ACCESS_KEYS.items():
            keys_list.append({
                "key": key,
                "duration_seconds": int(info["duration"].total_seconds()),
                "created_at": info["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": (info["created_at"] + info["duration"]).strftime("%Y-%m-%d %H:%M:%S")
            })
        return {"keys": keys_list}

    # ------------------------
    # Генерация нового ключа
    # duration_idx - индекс в KEY_DURATION_OPTIONS
    # ------------------------
    def create_key(self, duration_idx: int):
        if duration_idx < 0 or duration_idx >= len(KEY_DURATION_OPTIONS):
            return {"error": "Invalid duration index"}

        label, duration = KEY_DURATION_OPTIONS[duration_idx]
        new_key = generate_key(duration)

        return {
            "key": new_key,
            "duration_label": label,
            "expires_at": (datetime.now() + duration).strftime("%Y-%m-%d %H:%M:%S")
        }
