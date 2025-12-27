import psutil
import time
import os

START_TIME = time.time()

def get_metrics():
    try:
        cpu = psutil.cpu_percent(interval=0.3)
    except:
        cpu = 0

    try:
        vm = psutil.virtual_memory()
        ram_mb = round(vm.used / 1024 / 1024, 1)
        ram_percent = round(vm.percent, 1)
    except:
        ram_mb = 0
        ram_percent = 0

    try:
        load = round(os.getloadavg()[0], 2)
    except:
        load = 0

    try:
        threads = psutil.Process().num_threads()
    except:
        threads = 0

    uptime = int(time.time() - START_TIME)

    return {
        "cpu": cpu,
        "ram_mb": ram_mb,
        "ram_percent": ram_percent,
        "load_avg": load,
        "threads": threads,
        "uptime_sec": uptime
    }