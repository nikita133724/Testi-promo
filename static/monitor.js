const ably = new Ably.Realtime(ABLY_PUBLIC_KEY);
const channel = ably.channels.get('system-metrics');

const cpuCtx = document.getElementById('cpuChart').getContext('2d');
const ramCtx = document.getElementById('ramChart').getContext('2d');

let cpuData = [], ramData = [], labels = [];
let pendingMetrics = [];

// ----------------------------
// Инициализация графиков
const cpuChart = new Chart(cpuCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'CPU %', data: cpuData, borderColor: 'red', fill: false }] },
    options: { animation: { duration: 300 }, responsive: true, scales: { x: { display: false } } }
});

const ramChart = new Chart(ramCtx, {
    type: 'line',
    data: { labels, datasets: [{ label: 'RAM %', data: ramData, borderColor: 'blue', fill: false }] },
    options: { animation: { duration: 300 }, responsive: true, scales: { x: { display: false } } }
});

// ----------------------------
// Входим в Presence после подключения
async function enterPresence() {
    try {
        await channel.presence.enter({ viewing: true });
        console.log("Entered Presence (monitoring active)");
    } catch (err) {
        console.error("Error entering presence:", err);
    }
}

// Выходим из Presence при уходе со страницы
async function leavePresence() {
    try {
        await channel.presence.leave();
        console.log("Left Presence (monitoring stopped)");
    } catch (err) {
        console.error("Error leaving presence:", err);
    }
}

ably.connection.on('connected', enterPresence);

// Обработка закрытия вкладки / перехода / потери соединения
window.addEventListener("beforeunload", leavePresence);
window.addEventListener("pagehide", leavePresence);

// ----------------------------
// Подписка на метрики
channel.subscribe('metrics', msg => {
    let d = msg.data;
    if (typeof d === 'string') d = JSON.parse(d);
    pendingMetrics.push(d);
});

// ----------------------------
// Функция обновления графиков и таблицы
function updateCharts() {
    if (!pendingMetrics.length) return;
    const last = pendingMetrics[pendingMetrics.length - 1];

    labels.push(new Date().toLocaleTimeString());
    cpuData.push(last.cpu);
    ramData.push(last.ram_percent);

    if (labels.length > 300) {
        labels.shift();
        cpuData.shift();
        ramData.shift();
    }

    cpuChart.update();
    ramChart.update();

    document.getElementById("cpu").innerText = last.cpu + " %";
    document.getElementById("ram").innerText = `${last.ram_mb} MB (${last.ram_percent}%)`;
    document.getElementById("load").innerText = last.load_avg;
    document.getElementById("threads").innerText = last.threads;

    const h = Math.floor(last.uptime_sec / 3600);
    const m = Math.floor((last.uptime_sec % 3600) / 60);
    const s = last.uptime_sec % 60;
    document.getElementById("uptime").innerText = `${h}h ${m}m ${s}s`;

    pendingMetrics = [];
}

// ----------------------------
// Интервал обновления графиков
setInterval(updateCharts, 500);

// ----------------------------
// Загрузка истории метрик при заходе на страницу
async function initMonitor() {
    try {
        const history = await fetch('/admin/monitor/history').then(r => r.json());
        history.forEach(p => pendingMetrics.push(p));
    } catch (err) {
        console.error("Failed to load monitor history:", err);
    }
}

initMonitor();