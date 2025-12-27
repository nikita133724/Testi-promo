async function updateMetrics() {
    const res = await fetch('/admin/monitor/data');
    const data = await res.json();

    const cells = document.querySelectorAll("#row td");

    cells[0].innerText = data.cpu + " %";
    cells[1].innerText = data.ram_mb + " MB (" + data.ram_percent + "%)";
    cells[2].innerText = data.load_avg.toFixed(2);
    cells[3].innerText = data.threads;
    
    let h = Math.floor(data.uptime_sec / 3600);
    let m = Math.floor((data.uptime_sec % 3600) / 60);
    let s = data.uptime_sec % 60;

    cells[4].innerText = `${h}h ${m}m ${s}s`;
}

setInterval(updateMetrics, 2000);
updateMetrics();