import psutil
import time
import os

BOOT_TIME = time.time()

def get_metrics():
    return {
        "cpu": psutil.cpu_percent(interval=0.3),
        "ram_mb": round(psutil.virtual_memory().used / 1024 / 1024, 1),
        "ram_percent": psutil.virtual_memory().percent,
        "load_avg": os.getloadavg()[0],
        "threads": psutil.Process().num_threads(),
        "uptime_sec": int(time.time() - BOOT_TIME)
    }