const cpuCtx = document.getElementById('cpuChart').getContext('2d');
const ramCtx = document.getElementById('ramChart').getContext('2d');

const cpuData = [];
const ramData = [];
const labels = [];

const cpuChart = new Chart(cpuCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'CPU %', data: cpuData }] },
    options: { animation: false }
});

const ramChart = new Chart(ramCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'RAM %', data: ramData }] },
    options: { animation: false }
});

// Ably
const ably = new Ably.Realtime(ABLY_PUBLIC_KEY);
const channel = ably.channels.get('system-metrics');

async function initMonitor() {
    // 🔹 1. Enter presence (отмечаем, что пользователь на странице)
    await channel.presence.enter({ viewing: true }).catch(err => console.error("Presence enter error:", err));

    // 🔹 2. Получаем историю метрик
    const history = await fetch('/admin/monitor/history').then(r => r.json());
    history.forEach(p => {
        labels.push('');
        cpuData.push(p.cpu);
        ramData.push(p.ram_percent);
    });

    cpuChart.update();
    ramChart.update();

    // 🔹 3. Подписка на новые метрики
    channel.subscribe('metrics', msg => {
        const d = msg.data;

        if (labels.length > 300) {
            labels.shift();
            cpuData.shift();
            ramData.shift();
        }

        labels.push('');
        cpuData.push(d.cpu);
        ramData.push(d.ram_percent);

        // Обновляем текстовые значения
        document.getElementById("cpu").innerText = d.cpu + " %";
        document.getElementById("ram").innerText = d.ram_mb + " MB (" + d.ram_percent + "%)";
        document.getElementById("load").innerText = d.load_avg;
        document.getElementById("threads").innerText = d.threads;
        
        const h = Math.floor(d.uptime_sec / 3600);
        const m = Math.floor((d.uptime_sec % 3600) / 60);
        const s = d.uptime_sec % 60;
        document.getElementById("uptime").innerText = `${h}h ${m}m ${s}s`;
        
        cpuChart.update();
        ramChart.update();
    });
}

// 🔹 Уходим со страницы — оставляем Presence чистым
window.addEventListener("beforeunload", () => {
    channel.presence.leave().catch(err => console.error("Presence leave error:", err));
});

// Запуск мониторинга
initMonitor();