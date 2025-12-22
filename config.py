# =========================
# API настройки
# =========================
API_URL_BET = "https://cs2run.app/v1/rollrun/create"
API_URL_PROMO_ACTIVATE = "https://cs2run.app/discount"
API_URL_REFRESH = "https://cs2run.app/auth/refresh-token"

# =========================
# Telegram Bot
# =========================
TELEGRAM_BOT_TOKEN = "8061115919:AAE58otKx5hOyYA2rbCpU-jbfFnGl0aixO4"
REDIS_URL = "rediss://:AVplAAIncDJjZDA0YTNmNTE1ZmI0MDdhOTk1MTkxMWI2YzdmMWQ1ZXAyMjMxNDE@massive-scorpion-23141.upstash.io:6379"

# =========================
# Telegram Client для чтения каналов
# =========================
TELEGRAM_SESSION_FILE = "session.session"  # файл сессии аккаунта
TELEGRAM_API_ID = 37747270                  # твой API ID
TELEGRAM_API_HASH = "ed1f2f4080055b445818d6235c12d4fc"

CHANNEL_ORDINARY = "@jcivipvvuov"
CHANNEL_SPECIAL = "@run_case" #"@SpeshkaCodes"

# =========================
# Логика работы
# =========================
LOGIC_BALANCE_ECONOMY = True  # True - экономим баланс, False - скорость
ALLOW_NON_STANDARD = True     # обрабатывать нестандартные номиналы

# =========================
# Номиналы (доллары)
# =========================
ACTIVE_NOMINALS = [0.25, 0.5, 1, 2, 3, 5, 20]

# =========================
# Тайминги (секунды)
# =========================
WAIT_AFTER_ACTIVATE = 0.3     # пауза после активации/ставки
WAIT_BET_INTERVAL = 0.3       # пауза перед следующим промокодом
TIMEOUT_SERVER = 15           # ожидание ответа сервера

# =========================
# Токены
# =========================
ACCESS_TOKEN = ""
REFRESH_TOKEN = ""
