async function updateMetrics() {
    try {
        const res = await fetch('/admin/monitor/data');
        const data = await res.json();

        document.getElementById('cpu').innerText = data.cpu.toFixed(1) + " %";
        document.getElementById('ram').innerText =
            data.ram_mb.toFixed(0) + " MB (" + data.ram_percent.toFixed(1) + "%)";
        document.getElementById('load').innerText = data.load_avg.toFixed(2);
        document.getElementById('threads').innerText = data.threads;

        const h = Math.floor(data.uptime_sec / 3600);
        const m = Math.floor((data.uptime_sec % 3600) / 60);
        const s = data.uptime_sec % 60;

        document.getElementById('uptime').innerText = `${h}h ${m}m ${s}s`;

    } catch (e) {
        console.error("Monitor error:", e);
    }
}

setInterval(updateMetrics, 2000);
updateMetrics();