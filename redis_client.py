import redis
from config import REDIS_URL

# Общий Redis для всех модулей
r = redis.from_url(REDIS_URL)