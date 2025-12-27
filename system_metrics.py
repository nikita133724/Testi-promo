import psutil
import time
import os

BOOT_TIME = time.time()
process = psutil.Process(os.getpid())

def get_metrics():
    mem = psutil.virtual_memory()
    app_mem = process.memory_info().rss / 1024 / 1024  # реальная память ТВОЕГО приложения

    return {
        "cpu": psutil.cpu_percent(interval=0.3),

        # общая память системы
        "ram_mb": round(mem.used / 1024 / 1024, 1),
        "ram_percent": mem.percent,

        # 🔥 главное — сколько ест ТВОЙ процесс
        "app_ram_mb": round(app_mem, 1),

        "load_avg": os.getloadavg()[0],
        "threads": process.num_threads(),
        "uptime_sec": int(time.time() - BOOT_TIME)
    }