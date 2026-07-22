// Sentinel360 Client-side Script
document.addEventListener("DOMContentLoaded", () => {
    // Determine page context
    const serverGrid = document.getElementById("servers-container");
    const isDetailPage = document.getElementById("server-detail-container");

    if (serverGrid) {
        initDashboard();
    } else if (isDetailPage) {
        initDetailPage();
    }
});

// ==========================================
// DASHBOARD VIEW LOGIC
// ==========================================

function initDashboard() {
    // DOM Elements
    const addServerBtn = document.getElementById("add-server-btn");
    const addModal = document.getElementById("add-server-modal");
    const addForm = document.getElementById("add-server-form");
    const monitorTypeSelect = document.getElementById("monitor_type");
    const snmpFields = document.getElementById("snmp-config-fields");
    const apiKeyModal = document.getElementById("api-key-modal");
    const apiKeyVal = document.getElementById("api-key-val");
    const copyKeyBtn = document.getElementById("copy-key-btn");
    const alertsContainer = document.getElementById("alerts-container");
    const cancelModalBtn = document.getElementById("cancel-modal-btn");

    // Poll interval IDs
    let serverPollInterval;
    let alertPollInterval;

    // Toggle SNMP fields based on monitor type
    monitorTypeSelect.addEventListener("change", () => {
        if (monitorTypeSelect.value === "snmp") {
            snmpFields.style.display = "block";
            // Require fields
            document.getElementById("snmp_community").required = true;
            document.getElementById("snmp_port").required = true;
        } else {
            snmpFields.style.display = "none";
            document.getElementById("snmp_community").required = false;
            document.getElementById("snmp_port").required = false;
        }
    });

    // Modal Control
    addServerBtn.addEventListener("click", () => {
        addForm.reset();
        snmpFields.style.display = "none";
        addModal.showModal();
    });

    cancelModalBtn.addEventListener("click", () => {
        addModal.close();
    });

    // Fetch and Render Servers
    async function loadServers() {
        try {
            const res = await fetch("/api/servers");
            if (!res.ok) throw new Error("Failed to fetch servers");
            const servers = await res.json();
            renderServers(servers);
        } catch (error) {
            console.error("Error loading servers:", error);
        }
    }

    function renderServers(servers) {
        const container = document.getElementById("servers-container");
        if (servers.length === 0) {
            container.innerHTML = `
                <div class="card" style="grid-column: 1/-1; text-align: center; padding: 3rem;">
                    <div style="font-size: 2.5rem; margin-bottom: 1rem; opacity: 0.4;">🖥️</div>
                    <h3 style="margin-bottom: 0.5rem;">Belum Ada Server</h3>
                    <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Daftarkan server atau perangkat Anda untuk mulai memantau.</p>
                    <button class="btn btn-primary" onclick="document.getElementById('add-server-modal').showModal()">Tambah Server</button>
                </div>
            `;
            return;
        }

        container.innerHTML = servers.map(server => {
            const isOnline = server.status === "online";
            const isOffline = server.status === "offline";
            const statusClass = isOnline ? "status-online" : (isOffline ? "status-offline" : "status-unknown");
            const statusText = server.status;
            
            // Format OS & Last Seen
            const osStr = server.os_info || "Checking...";
            const lastSeenStr = server.last_seen ? new Date(server.last_seen).toLocaleString() : "Never";
            
            // Build metrics UI if online and has agent/SNMP metrics
            let metricsHtml = "";
            if (isOnline && (server.monitor_type === "agent" || server.monitor_type === "snmp")) {
                const cpu = server.cpu_usage !== null ? Math.round(server.cpu_usage) : null;
                const ram = server.ram_usage !== null ? Math.round(server.ram_usage) : null;
                const disk = server.disk_usage !== null ? Math.round(server.disk_usage) : null;
                
                const getBarColor = (val) => {
                    if (val >= 90) return "danger";
                    if (val >= 70) return "warning";
                    return "normal";
                };

                metricsHtml = `
                    <div class="metric-bar-group">
                        ${cpu !== null ? `
                        <div>
                            <div class="metric-label-container">
                                <span class="metric-label">CPU Load</span>
                                <span class="metric-value">${cpu}%</span>
                            </div>
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill ${getBarColor(cpu)}" style="width: ${cpu}%"></div>
                            </div>
                        </div>` : ""}
                        
                        ${ram !== null ? `
                        <div>
                            <div class="metric-label-container">
                                <span class="metric-label">RAM Usage</span>
                                <span class="metric-value">${ram}%</span>
                            </div>
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill ${getBarColor(ram)}" style="width: ${ram}%"></div>
                            </div>
                        </div>` : ""}
                        
                        ${disk !== null ? `
                        <div>
                            <div class="metric-label-container">
                                <span class="metric-label">Disk Space</span>
                                <span class="metric-value">${disk}%</span>
                            </div>
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill ${getBarColor(disk)}" style="width: ${disk}%"></div>
                            </div>
                        </div>` : ""}
                    </div>
                `;
            } else if (isOnline && server.monitor_type === "ping") {
                metricsHtml = `
                    <div style="padding: 1rem 0; text-align: center; color: var(--online); font-size: 0.85rem; font-weight: 500;">
                        ✓ ICMP Network Link OK
                    </div>
                `;
            } else {
                metricsHtml = `
                    <div style="padding: 1.5rem 0; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
                        No data available (${server.status})
                    </div>
                `;
            }

            return `
                <div class="card ${statusClass}">
                    <div class="card-header">
                        <div class="server-title-container">
                            <a href="/server/${server.id}" class="server-name">${server.name}</a>
                            <span class="server-ip">${server.ip_address}</span>
                        </div>
                        <span class="status-badge ${statusClass}">
                            <span class="dot"></span> ${statusText}
                        </span>
                    </div>
                    
                    <div class="server-meta-info">
                        <div><strong>OS:</strong> ${osStr}</div>
                        <div><strong>Uptime:</strong> ${server.uptime || "N/A"}</div>
                        <div><strong>Last Seen:</strong> ${lastSeenStr}</div>
                    </div>
                    
                    ${metricsHtml}
                    
                    <div class="server-footer">
                        <span class="monitor-type-badge">${server.monitor_type}</span>
                        <a href="/server/${server.id}" class="btn btn-secondary" style="padding: 0.35rem 0.75rem; font-size: 0.75rem;">Detail & Grafik</a>
                    </div>
                </div>
            `;
        }).join("");
    }

    // Submit Add Server Form
    addForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const payload = {
            name: document.getElementById("name").value,
            ip_address: document.getElementById("ip_address").value,
            monitor_type: monitorTypeSelect.value,
        };

        if (payload.monitor_type === "snmp") {
            payload.snmp_community = document.getElementById("snmp_community").value;
            payload.snmp_port = parseInt(document.getElementById("snmp_port").value, 10);
            payload.snmp_version = document.getElementById("snmp_version").value;
        }

        try {
            const res = await fetch("/api/servers", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || "Gagal menyimpan server.");
            }

            const newServer = await res.json();
            addModal.close();
            loadServers();

            // If agent monitor type, show API Key popup
            if (newServer.monitor_type === "agent") {
                apiKeyVal.textContent = newServer.api_key;
                apiKeyModal.showModal();
            }
        } catch (error) {
            alert("Error: " + error.message);
        }
    });

    // Copy API Key
    copyKeyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(apiKeyVal.textContent);
        copyKeyBtn.textContent = "Copied!";
        setTimeout(() => {
            copyKeyBtn.textContent = "Copy";
        }, 2000);
    });

    document.getElementById("close-api-key-modal").addEventListener("click", () => {
        apiKeyModal.close();
    });

    // Load & Render Alerts
    async function loadAlerts() {
        try {
            const res = await fetch("/api/alerts?resolved=false");
            if (!res.ok) throw new Error("Failed to fetch alerts");
            const alerts = await res.json();
            renderAlerts(alerts);
        } catch (error) {
            console.error("Error loading alerts:", error);
        }
    }

    function renderAlerts(alerts) {
        if (alerts.length === 0) {
            alertsContainer.innerHTML = `
                <div style="text-align: center; padding: 2rem 0; color: var(--text-muted); font-size: 0.85rem;">
                    Tidak ada alarm aktif. Sistem aman.
                </div>
            `;
            return;
        }

        alertsContainer.innerHTML = alerts.map(alert => {
            const timeStr = new Date(alert.timestamp).toLocaleTimeString();
            return `
                <div class="alert-item">
                    <span class="alert-msg">${alert.message}</span>
                    <span class="alert-time">⚠️ Aktif pada: ${timeStr}</span>
                    <button class="btn btn-secondary" style="align-self: flex-end; padding: 0.25rem 0.5rem; font-size: 0.7rem; border-color: rgba(239, 68, 68, 0.2);" onclick="resolveAlert(${alert.id})">
                        Selesaikan
                    </button>
                </div>
            `;
        }).join("");
    }

    window.resolveAlert = async function(alertId) {
        try {
            const res = await fetch(`/api/alerts/${alertId}/resolve`, { method: "POST" });
            if (!res.ok) throw new Error("Gagal menyelesaikan alarm");
            loadAlerts();
            loadServers();
        } catch (error) {
            alert(error.message);
        }
    };

    // Initial load and start interval polling
    loadServers();
    loadAlerts();
    serverPollInterval = setInterval(loadServers, 5000);
    alertPollInterval = setInterval(loadAlerts, 5000);

    // Stop intervals when page changes (navigating away)
    window.addEventListener("beforeunload", () => {
        clearInterval(serverPollInterval);
        clearInterval(alertPollInterval);
    });
}

// ==========================================
// DETAIL VIEW LOGIC
// ==========================================

function initDetailPage() {
    const serverId = window.serverId; // Defined in the HTML template
    let metricsChartCpu, metricsChartRam, metricsChartDisk, metricsChartNet;
    let detailPollInterval;

    async function loadServerDetails() {
        try {
            // Load Server Basic info
            const sRes = await fetch(`/api/servers/${serverId}`);
            if (!sRes.ok) throw new Error("Server not found");
            const server = await sRes.json();
            
            // Fill header info
            document.getElementById("detail-name").textContent = server.name;
            document.getElementById("detail-ip").textContent = server.ip_address;
            document.getElementById("detail-type").textContent = server.monitor_type.toUpperCase();
            
            const statusEl = document.getElementById("detail-status");
            statusEl.className = `status-badge ${server.status === "online" ? "status-online" : (server.status === "offline" ? "status-offline" : "status-unknown")}`;
            statusEl.innerHTML = `<span class="dot"></span> ${server.status}`;
            
            document.getElementById("detail-os").textContent = server.os_info || "N/A";
            document.getElementById("detail-uptime").textContent = server.uptime || "N/A";
            document.getElementById("detail-seen").textContent = server.last_seen ? new Date(server.last_seen).toLocaleString() : "Never";
            
            // Show token details if agent type
            const agentTokenSec = document.getElementById("agent-token-section");
            if (server.monitor_type === "agent" && agentTokenSec) {
                agentTokenSec.style.display = "block";
                document.getElementById("agent-key-display-val").textContent = server.api_key;
            }
        } catch (error) {
            console.error("Error loading server details:", error);
            document.getElementById("server-detail-container").innerHTML = `
                <div class="card" style="text-align: center; padding: 4rem;">
                    <h2 style="color: var(--offline)">Server Tidak Ditemukan</h2>
                    <p style="margin-top: 1rem;">Server dengan ID ${serverId} tidak terdaftar di sistem.</p>
                    <a href="/" class="btn btn-primary" style="margin-top: 2rem;">Kembali ke Dashboard</a>
                </div>
            `;
        }
    }

    // Set copy button event
    const copyKeyBtn = document.getElementById("copy-detail-key-btn");
    if (copyKeyBtn) {
        copyKeyBtn.addEventListener("click", () => {
            const key = document.getElementById("agent-key-display-val").textContent;
            navigator.clipboard.writeText(key);
            copyKeyBtn.textContent = "Copied!";
            setTimeout(() => { copyKeyBtn.textContent = "Copy API Key"; }, 2000);
        });
    }

    // Fetch and Draw Historical Charts
    async function loadMetrics() {
        const selectHours = document.getElementById("range-select")?.value || 12;
        try {
            const res = await fetch(`/api/servers/${serverId}/metrics?hours=${selectHours}`);
            if (!res.ok) throw new Error("Failed to fetch metrics");
            const metrics = await res.json();
            
            drawCharts(metrics);
        } catch (error) {
            console.error("Error loading metrics:", error);
        }
    }

    function drawCharts(metrics) {
        // Extract data lists
        const labels = metrics.map(m => new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        const cpuData = metrics.map(m => m.cpu_usage);
        const ramData = metrics.map(m => m.ram_usage);
        const diskData = metrics.map(m => m.disk_usage);
        
        // Latency (Ping) or Network speed (Agent)
        const netRxData = metrics.map(m => m.network_rx);
        const netTxData = metrics.map(m => m.network_tx);
        const latencyData = metrics.map(m => m.latency);

        // Chart styling templates
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: { color: "#94a3b8", maxTicksLimit: 8 }
                },
                y: {
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: { color: "#94a3b8" },
                    min: 0,
                    max: 100
                }
            }
        };

        // 1. CPU Chart
        if (metricsChartCpu) metricsChartCpu.destroy();
        const ctxCpu = document.getElementById("cpu-chart")?.getContext("2d");
        if (ctxCpu) {
            metricsChartCpu = new Chart(ctxCpu, {
                type: "line",
                data: {
                    labels,
                    datasets: [{
                        data: cpuData,
                        borderColor: "#6366f1",
                        backgroundColor: "rgba(99, 102, 241, 0.1)",
                        fill: true,
                        tension: 0.3,
                        borderWidth: 2
                    }]
                },
                options: chartOptions
            });
        }

        // 2. RAM Chart
        if (metricsChartRam) metricsChartRam.destroy();
        const ctxRam = document.getElementById("ram-chart")?.getContext("2d");
        if (ctxRam) {
            metricsChartRam = new Chart(ctxRam, {
                type: "line",
                data: {
                    labels,
                    datasets: [{
                        data: ramData,
                        borderColor: "#a855f7",
                        backgroundColor: "rgba(168, 85, 247, 0.1)",
                        fill: true,
                        tension: 0.3,
                        borderWidth: 2
                    }]
                },
                options: chartOptions
            });
        }

        // 3. Disk Chart
        if (metricsChartDisk) metricsChartDisk.destroy();
        const ctxDisk = document.getElementById("disk-chart")?.getContext("2d");
        if (ctxDisk) {
            metricsChartDisk = new Chart(ctxDisk, {
                type: "line",
                data: {
                    labels,
                    datasets: [{
                        data: diskData,
                        borderColor: "#10b981",
                        backgroundColor: "rgba(16, 185, 129, 0.1)",
                        fill: true,
                        tension: 0.3,
                        borderWidth: 2
                    }]
                },
                options: chartOptions
            });
        }

        // 4. Secondary Metric Chart (Latency or Net Speed)
        if (metricsChartNet) metricsChartNet.destroy();
        const ctxNet = document.getElementById("net-chart")?.getContext("2d");
        if (ctxNet) {
            // Determine type of secondary chart
            const hasPingData = latencyData.some(v => v !== null);
            const netOptions = JSON.parse(JSON.stringify(chartOptions));
            delete netOptions.scales.y.max; // Allow auto scale

            let datasets = [];
            if (hasPingData) {
                datasets = [{
                    data: latencyData,
                    borderColor: "#3b82f6",
                    backgroundColor: "rgba(59, 130, 246, 0.1)",
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2
                }];
                document.getElementById("net-chart-title").textContent = "Ping Latency (ms)";
            } else {
                datasets = [
                    {
                        label: "RX Speed (Kbps)",
                        data: netRxData,
                        borderColor: "#ec4899",
                        tension: 0.3,
                        borderWidth: 2
                    },
                    {
                        label: "TX Speed (Kbps)",
                        data: netTxData,
                        borderColor: "#3b82f6",
                        tension: 0.3,
                        borderWidth: 2
                    }
                ];
                netOptions.plugins.legend = { display: true, labels: { color: "#94a3b8" } };
                document.getElementById("net-chart-title").textContent = "Network Speed (Kbps)";
            }

            metricsChartNet = new Chart(ctxNet, {
                type: "line",
                data: { labels, datasets },
                options: netOptions
            });
        }
    }

    // Delete Server Trigger
    const deleteBtn = document.getElementById("delete-server-btn");
    if (deleteBtn) {
        deleteBtn.addEventListener("click", async () => {
            if (confirm("Apakah Anda yakin ingin menghapus server ini dari Sentinel360? Semua data history performa akan dihapus permanen.")) {
                try {
                    const res = await fetch(`/api/servers/${serverId}`, { method: "DELETE" });
                    if (!res.ok) throw new Error("Gagal menghapus server");
                    window.location.href = "/";
                } catch (error) {
                    alert(error.message);
                }
            }
        });
    }

    // Range selector change
    const rangeSelect = document.getElementById("range-select");
    if (rangeSelect) {
        rangeSelect.addEventListener("change", loadMetrics);
    }

    // Initial load and start poll
    loadServerDetails();
    loadMetrics();
    detailPollInterval = setInterval(() => {
        loadServerDetails();
        loadMetrics();
    }, 5000);

    window.addEventListener("beforeunload", () => {
        clearInterval(detailPollInterval);
    });
}
