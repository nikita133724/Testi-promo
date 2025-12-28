const ably = new Ably.Realtime({ key: ABLY_PUBLIC_KEY, clientId: CLIENT_ID });
const channel = ably.channels.get('system-metrics');

const cpuCtx = document.getElementById('cpuChart').getContext('2d');
const ramCtx = document.getElementById('ramChart').getContext('2d');

let cpuData = [], ramData = [], labels = [];
let pendingMetrics = [];

// ----------------------------
// 🎨 Красивые и лёгкие графики
const commonOptions = {
    animation: { duration: 200 },
    responsive: false,
    maintainAspectRatio: true,
    scales: {
        x: { display: false },
        y: {
            beginAtZero: true,
            ticks: { color: "#ccc" },
            grid: { color: "rgba(255,255,255,0.05)" }
        }
    },
    plugins: {
        legend: { labels: { color: "#eee" } }
    }
};

const cpuChart = new Chart(cpuCtx, {
    type: 'line',
    data: {
        labels,
        datasets: [{
            label: 'CPU %',
            data: cpuData,
            borderColor: '#ff4d4f',
            backgroundColor: 'rgba(255,77,79,0.15)',
            tension: 0.3,
            fill: true,
            pointRadius: 0
        }]
    },
    options: commonOptions
});

const ramChart = new Chart(ramCtx, {
    type: 'line',
    data: {
        labels,
        datasets: [{
            label: 'RAM %',
            data: ramData,
            borderColor: '#4dabf7',
            backgroundColor: 'rgba(77,171,247,0.15)',
            tension: 0.3,
            fill: true,
            pointRadius: 0
        }]
    },
    options: commonOptions
});

// ----------------------------
// Presence
async function enterPresence() {
    try { await channel.presence.enter({ viewing: true }); }
    catch (err) { console.error("Error entering presence:", err); }
}

async function leavePresence() {
    try { await channel.presence.leave(); }
    catch (err) { console.error("Error leaving presence:", err); }
}

ably.connection.on('connected', enterPresence);
ably.connection.on('disconnected', leavePresence);
window.addEventListener("beforeunload", leavePresence);
window.addEventListener("pagehide", leavePresence);

// ----------------------------
// Получение метрик
channel.subscribe('metrics', msg => {
    let d = msg.data;
    if (typeof d === 'string') d = JSON.parse(d);
    pendingMetrics.push(d);
});

// ----------------------------
// 📊 Обновление
function updateCharts() {
    if (!pendingMetrics.length) return;

    const last = pendingMetrics[pendingMetrics.length - 1];
    pendingMetrics = [];

    labels.push(new Date().toLocaleTimeString());
    cpuData.push(last.cpu);
    ramData.push(last.ram_percent);

    if (labels.length > 240) {
        labels.shift();
        cpuData.shift();
        ramData.shift();
    }

    cpuChart.update('none');
    ramChart.update('none');

    document.getElementById("cpu").innerText = last.cpu + " %";
    document.getElementById("ram").innerText = `${last.ram_mb} MB (${last.ram_percent}%)`;
    document.getElementById("load").innerText = last.load_avg;
    document.getElementById("threads").innerText = last.threads;

    const h = Math.floor(last.uptime_sec / 3600);
    const m = Math.floor((last.uptime_sec % 3600) / 60);
    const s = last.uptime_sec % 60;
    document.getElementById("uptime").innerText = `${h}h ${m}m ${s}s`;
}

// ----------------------------
// Интервал обновления
setInterval(updateCharts, 500);

// ----------------------------
// История при загрузке
async function initMonitor() {
    try {
        const history = await fetch('/admin/monitor/history').then(r => r.json());
        history.forEach(p => pendingMetrics.push(p));
    } catch (err) {
        console.error("Failed to load monitor history:", err);
    }
}

initMonitor();