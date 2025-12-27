const cpuCtx = document.getElementById('cpuChart').getContext('2d');
const ramCtx = document.getElementById('ramChart').getContext('2d');

const cpuData = [];
const ramData = [];
const labels = [];

const cpuChart = new Chart(cpuCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'CPU %', data: cpuData }] },
    options: { animation: false, responsive: true }
});

const ramChart = new Chart(ramCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'RAM %', data: ramData }] },
    options: { animation: false, responsive: true }
});

// Подключаемся к Ably
const ably = new Ably.Realtime(ABLY_PUBLIC_KEY);
const channel = ably.channels.get('system-metrics');

// Генерируем уникальный client_id для этого браузера
const client_id = Math.random().toString(36).substring(2);

// ----------------------------
// Отправка ping
function sendPing() {
    channel.publish('ping', { viewing: true, client_id })
        .catch(err => console.error("Ping error:", err));
}

// ----------------------------
// Обработка метрик
channel.subscribe('metrics', msg => {
    let d = msg.data;
    if (typeof d === 'string') d = JSON.parse(d);

    if (labels.length > 300) {
        labels.shift();
        cpuData.shift();
        ramData.shift();
    }

    const now = new Date();
    labels.push(now.toLocaleTimeString());
    cpuData.push(d.cpu);
    ramData.push(d.ram_percent);

    // Обновляем таблицу
    document.getElementById("cpu").innerText = d.cpu + " %";
    document.getElementById("ram").innerText = `${d.ram_mb} MB (${d.ram_percent}%)`;
    document.getElementById("load").innerText = d.load_avg;
    document.getElementById("threads").innerText = d.threads;

    const h = Math.floor(d.uptime_sec / 3600);
    const m = Math.floor((d.uptime_sec % 3600) / 60);
    const s = d.uptime_sec % 60;
    document.getElementById("uptime").innerText = `${h}h ${m}m ${s}s`;

    cpuChart.update();
    ramChart.update();
});

// ----------------------------
// Инициализация
async function initMonitor() {
    // Загружаем историю
    const history = await fetch('/admin/monitor/history').then(r => r.json());
    history.forEach(p => {
        labels.push('');
        cpuData.push(p.cpu);
        ramData.push(p.ram_percent);
    });
    cpuChart.update();
    ramChart.update();

    // Отправляем первый ping сразу
    sendPing();

    // Пинг каждые 20 секунд
    setInterval(sendPing, 20000);
}

// ----------------------------
// При уходе со страницы
window.addEventListener("beforeunload", () => {
    channel.presence.leave().catch(err => console.error(err));
});

// Запуск
initMonitor();