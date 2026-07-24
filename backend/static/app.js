// Sentinel360 Client-side Script
function parseUTC(dateStr) {
    if (!dateStr) return null;
    if (typeof dateStr === 'string' && !dateStr.endsWith('Z') && !dateStr.includes('+') && !/-\d{2}:\d{2}$/.test(dateStr)) {
        return new Date(dateStr + 'Z');
    }
    return new Date(dateStr);
}

document.addEventListener("DOMContentLoaded", () => {
    // Determine page context
    const serverGrid = document.getElementById("servers-container");
    const isDetailPage = document.getElementById("server-detail-container");

    // Global Change Password Handler
    const changePwdBtn = document.getElementById("change-pwd-btn");
    const changePwdModal = document.getElementById("change-password-modal");
    const cancelChangePwdBtn = document.getElementById("cancel-change-pwd-btn");
    const changePwdForm = document.getElementById("change-password-form");

    if (changePwdBtn && changePwdModal) {
        changePwdBtn.addEventListener("click", () => {
            changePwdForm.reset();
            changePwdModal.showModal();
        });
    }

    if (cancelChangePwdBtn && changePwdModal) {
        cancelChangePwdBtn.addEventListener("click", () => {
            changePwdModal.close();
        });
    }

    if (changePwdForm && changePwdModal) {
        changePwdForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const oldPassword = document.getElementById("old_password").value;
            const newPassword = document.getElementById("new_password").value;
            const confirmNewPassword = document.getElementById("confirm_new_password").value;

            if (newPassword !== confirmNewPassword) {
                alert("Password baru dan konfirmasi password tidak cocok!");
                return;
            }

            try {
                const res = await fetch("/api/user/change-password", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        old_password: oldPassword,
                        new_password: newPassword
                    })
                });

                const data = await res.json();
                if (!res.ok) {
                    throw new Error(data.detail || "Gagal mengubah password.");
                }

                alert("Password berhasil diubah!");
                changePwdModal.close();
            } catch (error) {
                alert("Error: " + error.message);
            }
        });
    }

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
    if (addServerBtn && typeof USER_ROLE !== "undefined" && USER_ROLE === "view") {
        addServerBtn.style.display = "none";
    }
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

    // Notification Setups Logic
    async function loadNotificationGroups() {
        try {
            const res = await fetch("/api/notifications");
            if (!res.ok) throw new Error("Gagal mengambil data setup notifikasi.");
            const configs = await res.json();

            // Populate checklists in forms
            const addServerChecklist = document.getElementById("add_server_groups_checklist");
            const addWebChecklist = document.getElementById("add_web_groups_checklist");
            
            const checklistsHtml = configs.length === 0 
                ? '<p style="color: var(--text-secondary); font-size: 0.8rem; margin: 0;">Belum ada setup notifikasi. Silakan buat di Alarm Settings.</p>'
                : configs.map(c => `
                    <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: var(--text-primary); cursor: pointer;">
                        <input type="checkbox" name="server_group_ids" value="${c.id}">
                        <strong>${c.name}</strong> (${c.type.toUpperCase()})
                    </label>
                `).join("");

            const checklistsWebHtml = configs.length === 0 
                ? '<p style="color: var(--text-secondary); font-size: 0.8rem; margin: 0;">Belum ada setup notifikasi. Silakan buat di Alarm Settings.</p>'
                : configs.map(c => `
                    <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: var(--text-primary); cursor: pointer;">
                        <input type="checkbox" name="web_group_ids" value="${c.id}">
                        <strong>${c.name}</strong> (${c.type.toUpperCase()})
                    </label>
                `).join("");
                
            if (addServerChecklist) addServerChecklist.innerHTML = checklistsHtml;
            if (addWebChecklist) addWebChecklist.innerHTML = checklistsWebHtml;
            
            // Populate setup list inside Settings modal
            const listContainer = document.getElementById("notifications-setup-list");
            if (listContainer) {
                if (configs.length === 0) {
                    listContainer.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.85rem; font-style: italic;">Belum ada setup notifikasi.</p>';
                } else {
                    listContainer.innerHTML = configs.map(c => `
                        <div style="display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--border-color); padding: 0.5rem 0.75rem; border-radius: 6px; margin-bottom: 0.5rem; background: rgba(255,255,255,0.02);">
                            <div>
                                <strong style="color: var(--text-primary); font-size: 0.9rem;">${c.name}</strong>
                                <span class="monitor-type-badge" style="font-size: 0.65rem; margin-left: 0.5rem;">${c.type.toUpperCase()}</span>
                                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">
                                    ${c.type === 'telegram' ? `Chat ID: ${c.telegram_chat_id || 'N/A'}` : ''}
                                    ${c.type === 'whatsapp' ? `Recipients: ${c.whatsapp_recipients || 'N/A'}` : ''}
                                    ${c.type === 'smtp' ? `Recipient: ${c.smtp_recipient || 'N/A'}` : ''}
                                </div>
                            </div>
                            <div style="display: flex; gap: 0.25rem;">
                                <button type="button" class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.7rem; border-color: var(--accent);" onclick="editNotificationConfig(${c.id})">Edit</button>
                                <button type="button" class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.7rem; border-color: rgba(239, 68, 68, 0.3); color: #ef4444;" onclick="deleteNotificationConfig(${c.id})">Hapus</button>
                            </div>
                        </div>
                    `).join("");
                }
            }
        } catch (error) {
            console.error("Error loading notifications setups:", error);
        }
    }

    // Type selection toggle inside modal
    const typeSelect = document.getElementById("new_notification_type");
    if (typeSelect) {
        typeSelect.addEventListener("change", () => {
            const val = typeSelect.value;
            document.getElementById("setup-telegram-fields").style.display = val === "telegram" ? "block" : "none";
            document.getElementById("setup-whatsapp-fields").style.display = val === "whatsapp" ? "block" : "none";
            document.getElementById("setup-smtp-fields").style.display = val === "smtp" ? "block" : "none";
        });
    }

    // Reset notification setup form
    window.resetNotificationForm = function() {
        const form = document.getElementById("notification-provider-form");
        if (form) form.reset();
        document.getElementById("edit_notification_id").value = "";
        document.getElementById("setup-form-title").textContent = "Buat Setup Notifikasi Baru";
        document.getElementById("test-notification-btn").style.display = "none";
        document.getElementById("cancel-edit-notification-btn").style.display = "none";
        
        // Reset sub-section visibility
        if (typeSelect) {
            typeSelect.value = "telegram";
            document.getElementById("setup-telegram-fields").style.display = "block";
            document.getElementById("setup-whatsapp-fields").style.display = "none";
            document.getElementById("setup-smtp-fields").style.display = "none";
        }
    };

    // Edit Notification Setup
    window.editNotificationConfig = async function(id) {
        try {
            const res = await fetch("/api/notifications");
            if (!res.ok) throw new Error("Gagal mengambil data setups.");
            const configs = await res.json();
            const config = configs.find(c => c.id === id);
            if (!config) return;

            document.getElementById("edit_notification_id").value = config.id;
            document.getElementById("new_notification_name").value = config.name;
            typeSelect.value = config.type;
            
            // Toggle visibility
            document.getElementById("setup-telegram-fields").style.display = config.type === "telegram" ? "block" : "none";
            document.getElementById("setup-whatsapp-fields").style.display = config.type === "whatsapp" ? "block" : "none";
            document.getElementById("setup-smtp-fields").style.display = config.type === "smtp" ? "block" : "none";

            // Populate fields
            document.getElementById("new_tele_bot_token").value = config.telegram_bot_token || "";
            document.getElementById("new_tele_chat_id").value = config.telegram_chat_id || "";
            
            document.getElementById("new_wa_webhook_url").value = config.whatsapp_webhook_url || "";
            document.getElementById("new_wa_token").value = config.whatsapp_token || "";
            document.getElementById("new_wa_session_id").value = config.whatsapp_session_id || "";
            document.getElementById("new_wa_recipients").value = config.whatsapp_recipients || "";
            
            document.getElementById("new_smtp_host").value = config.smtp_host || "";
            document.getElementById("new_smtp_port").value = config.smtp_port || 587;
            document.getElementById("new_smtp_username").value = config.smtp_username || "";
            document.getElementById("new_smtp_password").value = config.smtp_password || "";
            document.getElementById("new_smtp_sender").value = config.smtp_sender || "";
            document.getElementById("new_smtp_recipient").value = config.smtp_recipient || "";

            // Update form display state
            document.getElementById("setup-form-title").textContent = "Edit Setup Notifikasi";
            document.getElementById("test-notification-btn").style.display = "block";
            document.getElementById("cancel-edit-notification-btn").style.display = "block";
        } catch (error) {
            alert(error.message);
        }
    };

    // Delete Notification Setup
    window.deleteNotificationConfig = async function(id) {
        if (!confirm("Apakah Anda yakin ingin menghapus setup notifikasi ini?")) return;
        try {
            const res = await fetch(`/api/notifications/${id}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Gagal menghapus setup notifikasi.");
            resetNotificationForm();
            await loadNotificationGroups();
        } catch (error) {
            alert(error.message);
        }
    };

    // Save Notification Setup
    const saveNotificationBtn = document.getElementById("save-notification-btn");
    if (saveNotificationBtn) {
        saveNotificationBtn.addEventListener("click", async () => {
            const id = document.getElementById("edit_notification_id").value;
            const name = document.getElementById("new_notification_name").value;
            const type = typeSelect.value;
            
            if (!name) {
                alert("Nama setup wajib diisi!");
                return;
            }

            const payload = {
                name: name,
                type: type,
                is_enabled: true,
                telegram_bot_token: document.getElementById("new_tele_bot_token").value || null,
                telegram_chat_id: document.getElementById("new_tele_chat_id").value || null,
                whatsapp_webhook_url: document.getElementById("new_wa_webhook_url").value || null,
                whatsapp_token: document.getElementById("new_wa_token").value || null,
                whatsapp_session_id: document.getElementById("new_wa_session_id").value || null,
                whatsapp_recipients: document.getElementById("new_wa_recipients").value || null,
                smtp_host: document.getElementById("new_smtp_host").value || null,
                smtp_port: parseInt(document.getElementById("new_smtp_port").value, 10) || 587,
                smtp_username: document.getElementById("new_smtp_username").value || null,
                smtp_password: document.getElementById("new_smtp_password").value || null,
                smtp_sender: document.getElementById("new_smtp_sender").value || null,
                smtp_recipient: document.getElementById("new_smtp_recipient").value || null
            };

            try {
                let res;
                if (id) {
                    // Update
                    res = await fetch(`/api/notifications/${id}`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    });
                } else {
                    // Create
                    res = await fetch("/api/notifications", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload)
                    });
                }

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || "Gagal menyimpan setup notifikasi.");
                }

                alert("Setup notifikasi berhasil disimpan!");
                resetNotificationForm();
                await loadNotificationGroups();
            } catch (error) {
                alert(error.message);
            }
        });
    }

    // Cancel Edit
    const cancelEditBtn = document.getElementById("cancel-edit-notification-btn");
    if (cancelEditBtn) {
        cancelEditBtn.addEventListener("click", () => {
            resetNotificationForm();
        });
    }

    // Test Setup
    const testNotificationBtn = document.getElementById("test-notification-btn");
    if (testNotificationBtn) {
        testNotificationBtn.addEventListener("click", async () => {
            const id = document.getElementById("edit_notification_id").value;
            if (!id) return;
            testNotificationBtn.disabled = true;
            const originalText = testNotificationBtn.textContent;
            testNotificationBtn.textContent = "Mengirim...";
            try {
                const res = await fetch(`/api/notifications/${id}/test`, { method: "POST" });
                if (!res.ok) throw new Error("Gagal mengirim notifikasi uji coba.");
                alert("Notifikasi uji coba berhasil dikirim ke saluran setup ini!");
            } catch (error) {
                alert(error.message);
            } finally {
                testNotificationBtn.disabled = false;
                testNotificationBtn.textContent = originalText;
            }
        });
    }

    window.manageWebsiteNotifications = async function(webId) {
        const modal = document.getElementById("manage-website-groups-modal");
        const container = document.getElementById("web-groups-checklist");
        document.getElementById("manage_web_id").value = webId;

        // Fetch configs
        try {
            const gRes = await fetch("/api/notifications");
            if (!gRes.ok) throw new Error("Gagal mengambil data setup.");
            const allConfigs = await gRes.json();

            // Fetch website current active notifications
            const web = cachedWebsites.find(w => w.id === webId);
            const activeIds = (web && web.notifications) ? web.notifications.map(n => n.id) : [];

            if (allConfigs.length === 0) {
                container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.85rem; font-style: italic;">Belum ada setup notifikasi. Silakan buat di menu Notifikasi.</p>';
            } else {
                container.innerHTML = allConfigs.map(c => `
                    <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; color: var(--text-primary); cursor: pointer; border: 1px solid var(--border-color); padding: 0.4rem; border-radius: 4px; background: rgba(255,255,255,0.01);">
                        <input type="checkbox" name="manage_web_group_id" value="${c.id}" ${activeIds.includes(c.id) ? 'checked' : ''}>
                        <strong>${c.name}</strong> (${c.type.toUpperCase()})
                    </label>
                `).join("");
            }

            modal.showModal();
        } catch (error) {
            alert(error.message);
        }
    };

    // Cancel manage web groups modal
    const cancelWebGroupsBtn = document.getElementById("cancel-web-groups-btn");
    const webGroupsModal = document.getElementById("manage-website-groups-modal");
    if (cancelWebGroupsBtn && webGroupsModal) {
        cancelWebGroupsBtn.addEventListener("click", () => {
            webGroupsModal.close();
        });
    }

    const closeWebGroupsBottomBtn = document.getElementById("close-web-groups-bottom-btn");
    if (closeWebGroupsBottomBtn && webGroupsModal) {
        closeWebGroupsBottomBtn.addEventListener("click", () => {
            webGroupsModal.close();
        });
    }

    // Save website groups
    const saveWebGroupsBtn = document.getElementById("save-web-groups-btn");
    if (saveWebGroupsBtn && webGroupsModal) {
        saveWebGroupsBtn.addEventListener("click", async () => {
            const webId = document.getElementById("manage_web_id").value;
            const checkedBoxes = document.querySelectorAll('input[name="manage_web_group_id"]:checked');
            const notificationIds = Array.from(checkedBoxes).map(cb => parseInt(cb.value, 10));

            try {
                const res = await fetch(`/api/websites/${webId}/notifications`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(notificationIds)
                });
                if (!res.ok) throw new Error("Gagal menyimpan pengaturan notifikasi.");

                webGroupsModal.close();
                alert("Pengaturan notifikasi berhasil disimpan!");
                loadWebsites();
            } catch (error) {
                alert("Error: " + error.message);
            }
        });
    }

    // Load configurations on initial load
    loadNotificationGroups();

    let cachedServers = [];

    // Drag and drop handler
    function setupDragAndDrop() {
        const container = document.getElementById("servers-container");
        if (!container) return;

        let draggedItem = null;

        container.ondragstart = (e) => {
            const card = e.target.closest('[draggable="true"]');
            if (card) {
                draggedItem = card;
                e.dataTransfer.effectAllowed = 'move';
                card.style.opacity = '0.5';
            }
        };

        container.ondragend = (e) => {
            const card = e.target.closest('[draggable="true"]');
            if (card) {
                card.style.opacity = '1';
            }
            draggedItem = null;
            container.querySelectorAll('[draggable="true"]').forEach(c => {
                c.style.border = '';
            });
        };

        container.ondragover = (e) => {
            e.preventDefault();
            const card = e.target.closest('[draggable="true"]');
            if (card && card !== draggedItem) {
                e.dataTransfer.dropEffect = 'move';
                card.style.border = '2px dashed var(--accent)';
            }
        };

        container.ondragleave = (e) => {
            const card = e.target.closest('[draggable="true"]');
            if (card && card !== draggedItem) {
                card.style.border = '';
            }
        };

        container.ondrop = (e) => {
            e.preventDefault();
            const card = e.target.closest('[draggable="true"]');
            if (card && card !== draggedItem && draggedItem) {
                card.style.border = '';
                
                const draggedId = parseInt(draggedItem.getAttribute('data-id'), 10);
                const targetId = parseInt(card.getAttribute('data-id'), 10);
                
                const draggedIndex = cachedServers.findIndex(s => s.id === draggedId);
                const targetIndex = cachedServers.findIndex(s => s.id === targetId);
                
                if (draggedIndex !== -1 && targetIndex !== -1) {
                    const [removed] = cachedServers.splice(draggedIndex, 1);
                    cachedServers.splice(targetIndex, 0, removed);
                    
                    const newOrder = cachedServers.map(s => s.id);
                    localStorage.setItem('sentinel360_server_order', JSON.stringify(newOrder));
                    
                    renderServers(cachedServers);
                    setupDragAndDrop();
                }
            }
        };
    }

    // Fetch and Render Servers
    async function loadServers() {
        const container = document.getElementById("servers-container");
        try {
            const res = await fetch("/api/servers");
            if (res.status === 401) {
                window.location.href = "/login";
                return;
            }
            if (res.status === 403) {
                if (container) {
                    container.innerHTML = `
                        <div class="card" style="grid-column: 1/-1; text-align: center; padding: 3rem; border-color: rgba(239, 68, 68, 0.2);">
                            <div style="font-size: 2.5rem; margin-bottom: 1rem;">🔒</div>
                            <h3 style="margin-bottom: 0.5rem; color: #f87171;">Akses Ditolak</h3>
                            <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Anda tidak memiliki akses untuk melihat data server.</p>
                        </div>
                    `;
                }
                return;
            }
            if (!res.ok) {
                if (container) {
                    container.innerHTML = `
                        <div class="card" style="grid-column: 1/-1; text-align: center; padding: 3rem; border-color: rgba(239, 68, 68, 0.2);">
                            <div style="font-size: 2.5rem; margin-bottom: 1rem;">⚠️</div>
                            <h3 style="margin-bottom: 0.5rem; color: #f87171;">Gagal Memuat Data</h3>
                            <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Terjadi kesalahan saat memuat server (${res.status}).</p>
                            <button class="btn btn-secondary" onclick="loadServers()">Coba Lagi</button>
                        </div>
                    `;
                }
                throw new Error("Failed to fetch servers: " + res.status);
            }
            const servers = await res.json();
            
            // Sort according to saved order
            const savedOrder = localStorage.getItem('sentinel360_server_order');
            if (savedOrder) {
                try {
                    const orderArray = JSON.parse(savedOrder);
                    servers.sort((a, b) => {
                        let idxA = orderArray.indexOf(a.id);
                        let idxB = orderArray.indexOf(b.id);
                        if (idxA === -1) idxA = 9999;
                        if (idxB === -1) idxB = 9999;
                        return idxA - idxB;
                    });
                } catch(e) {
                    console.error("Error parsing saved order:", e);
                }
            }

            cachedServers = servers;
            renderServers(cachedServers);
            setupDragAndDrop();
        } catch (error) {
            console.error("Error loading servers:", error);
        }
    }

    function renderServers(servers) {
        const container = document.getElementById("servers-container");
        if (servers.length === 0) {
            const hideBtn = (typeof USER_ROLE !== "undefined" && USER_ROLE === "view") ? "display: none;" : "";
            container.innerHTML = `
                <div class="card" style="grid-column: 1/-1; text-align: center; padding: 3rem;">
                    <div style="font-size: 2.5rem; margin-bottom: 1rem; opacity: 0.4;">🖥️</div>
                    <h3 style="margin-bottom: 0.5rem;">Belum Ada Server</h3>
                    <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Daftarkan server atau perangkat Anda untuk mulai memantau.</p>
                    <button class="btn btn-primary" style="${hideBtn}" onclick="document.getElementById('add-server-modal').showModal()">Tambah Server</button>
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
            const lastSeenStr = server.last_seen ? parseUTC(server.last_seen).toLocaleString() : "Never";
            
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

                let ramInfoStr = "";
                if (ram !== null && server.ram_total) {
                    const ramTotal = parseFloat(server.ram_total);
                    const ramUsed = (ram / 100) * ramTotal;
                    ramInfoStr = ` <span style="font-size: 0.7rem; color: var(--text-muted); font-weight: normal;">(${ramUsed.toFixed(1)} GB / ${ramTotal.toFixed(1)} GB)</span>`;
                }

                let diskInfoStr = "";
                if (disk !== null && server.disk_total) {
                    const diskTotal = parseFloat(server.disk_total);
                    const diskUsed = (disk / 100) * diskTotal;
                    diskInfoStr = ` <span style="font-size: 0.7rem; color: var(--text-muted); font-weight: normal;">(${diskUsed.toFixed(1)} GB / ${diskTotal.toFixed(1)} GB)</span>`;
                }

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
                                <span class="metric-label">RAM Usage${ramInfoStr}</span>
                                <span class="metric-value">${ram}%</span>
                            </div>
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill ${getBarColor(ram)}" style="width: ${ram}%"></div>
                            </div>
                        </div>` : ""}
                        
                        ${disk !== null ? `
                        <div>
                            <div class="metric-label-container">
                                <span class="metric-label">Disk Space${diskInfoStr}</span>
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
                <div class="card ${statusClass}" draggable="true" data-id="${server.id}">
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
        
        const groupCheckboxes = document.querySelectorAll('input[name="server_group_ids"]:checked');
        const notification_group_ids = Array.from(groupCheckboxes).map(cb => parseInt(cb.value, 10));
        
        const payload = {
            name: document.getElementById("name").value,
            ip_address: document.getElementById("ip_address").value,
            monitor_type: monitorTypeSelect.value,
            notification_group_ids: notification_group_ids,
            failed_threshold: parseInt(document.getElementById("failed_threshold").value, 10) || 1,
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
            if (res.status === 401) {
                window.location.href = "/login";
                return;
            }
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

        const hideResolveBtn = (typeof USER_ROLE !== "undefined" && USER_ROLE === "view") ? "display: none;" : "";
        alertsContainer.innerHTML = alerts.map(alert => {
            const timeStr = parseUTC(alert.timestamp).toLocaleTimeString();
            return `
                <div class="alert-item">
                    <span class="alert-msg">${alert.message}</span>
                    <span class="alert-time">⚠️ Aktif pada: ${timeStr}</span>
                    <button class="btn btn-secondary" style="align-self: flex-end; padding: 0.25rem 0.5rem; font-size: 0.7rem; border-color: rgba(239, 68, 68, 0.2); ${hideResolveBtn}" onclick="resolveAlert(${alert.id})">
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

    let cachedWebsites = [];
    let websitePollInterval;

    const addWebsiteBtn = document.getElementById("add-website-btn");
    if (addWebsiteBtn && typeof USER_ROLE !== "undefined" && USER_ROLE === "view") {
        addWebsiteBtn.style.display = "none";
    }
    // Alarm Settings Modal Elements
    const alarmSettingsBtn = document.getElementById("settings-alarm-btn");
    const alarmSettingsModal = document.getElementById("alarm-settings-modal");
    const cancelAlarmSettingsBtn = document.getElementById("cancel-alarm-settings-btn");

    if (alarmSettingsBtn && alarmSettingsModal) {
        alarmSettingsBtn.addEventListener("click", async () => {
            resetNotificationForm();
            await loadNotificationGroups();
            alarmSettingsModal.showModal();
        });
    }

    if (cancelAlarmSettingsBtn && alarmSettingsModal) {
        cancelAlarmSettingsBtn.addEventListener("click", () => {
            alarmSettingsModal.close();
        });
    }

    const closeAlarmSettingsBottomBtn = document.getElementById("close-alarm-settings-bottom-btn");
    if (closeAlarmSettingsBottomBtn && alarmSettingsModal) {
        closeAlarmSettingsBottomBtn.addEventListener("click", () => {
            alarmSettingsModal.close();
        });
    }

    const addWebModal = document.getElementById("add-website-modal");
    const addWebForm = document.getElementById("add-website-form");
    const cancelWebModalBtn = document.getElementById("cancel-website-modal-btn");

    if (addWebsiteBtn && addWebModal) {
        addWebsiteBtn.addEventListener("click", () => {
            addWebForm.reset();
            addWebModal.showModal();
        });
    }

    if (cancelWebModalBtn && addWebModal) {
        cancelWebModalBtn.addEventListener("click", () => {
            addWebModal.close();
        });
    }

    if (addWebForm && addWebModal) {
        addWebForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const groupCheckboxes = document.querySelectorAll('input[name="web_group_ids"]:checked');
            const notification_group_ids = Array.from(groupCheckboxes).map(cb => parseInt(cb.value, 10));
            const failed_threshold = parseInt(document.getElementById("web_failed_threshold").value, 10) || 1;

            try {
                const res = await fetch("/api/websites", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name, url, notification_group_ids, failed_threshold })
                });

                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.detail || "Gagal menyimpan website.");
                }
                
                addWebForm.reset();
                document.querySelectorAll('input[name="web_group_ids"]').forEach(cb => cb.checked = false);
                addWebModal.close();
                loadWebsites();
            } catch (error) {
                alert("Error: " + error.message);
            }
        });
    }

    // Load Websites
    async function loadWebsites() {
        const container = document.getElementById("websites-container");
        if (!container) return;
        try {
            const res = await fetch("/api/websites");
            if (res.status === 401) {
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error("Failed to fetch websites");
            const websites = await res.json();

            // Sort according to saved order
            const savedOrder = localStorage.getItem('sentinel360_website_order');
            if (savedOrder) {
                try {
                    const orderArray = JSON.parse(savedOrder);
                    websites.sort((a, b) => {
                        let idxA = orderArray.indexOf(a.id);
                        let idxB = orderArray.indexOf(b.id);
                        if (idxA === -1) idxA = 9999;
                        if (idxB === -1) idxB = 9999;
                        return idxA - idxB;
                    });
                } catch(e) {
                    console.error("Error parsing saved website order:", e);
                }
            }

            cachedWebsites = websites;
            renderWebsites(cachedWebsites);
            setupWebDragAndDrop();
        } catch (error) {
            console.error("Error loading websites:", error);
        }
    }

    function renderWebsites(websites) {
        const container = document.getElementById("websites-container");
        if (!container) return;

        if (websites.length === 0) {
            container.innerHTML = `
                <div class="card" style="grid-column: 1/-1; text-align: center; padding: 2rem;">
                    <div style="font-size: 2.5rem; margin-bottom: 0.5rem; opacity: 0.4;">🌐</div>
                    <h4 style="margin-bottom: 0.5rem;">Belum Ada Website</h4>
                    <p style="color: var(--text-secondary); font-size: 0.8rem;">Daftarkan website/URL target untuk memantau status & SSL.</p>
                </div>
            `;
            return;
        }

        const hideDeleteBtn = (typeof USER_ROLE !== "undefined" && USER_ROLE === "view") ? "display: none;" : "";

        container.innerHTML = websites.map(web => {
            const isOnline = web.status === "online";
            const isOffline = web.status === "offline";
            const statusClass = isOnline ? "status-online" : (isOffline ? "status-offline" : "status-unknown");
            const statusText = web.status;

            // SSL details
            let sslBadge = "";
            if (web.ssl_status === "valid") {
                sslBadge = `<span class="monitor-type-badge" style="background: rgba(16, 185, 129, 0.15); border-color: var(--online); color: var(--online); font-size: 0.65rem;">SSL: ${web.ssl_days_left}d left</span>`;
            } else if (web.ssl_status === "warning") {
                sslBadge = `<span class="monitor-type-badge" style="background: rgba(245, 158, 11, 0.15); border-color: var(--warning); color: var(--warning); font-size: 0.65rem;">SSL Expiring: ${web.ssl_days_left}d</span>`;
            } else if (web.ssl_status === "expired") {
                sslBadge = `<span class="monitor-type-badge" style="background: rgba(239, 68, 68, 0.15); border-color: var(--offline); color: var(--offline); font-size: 0.65rem;">SSL EXPIRED</span>`;
            } else if (web.ssl_status === "invalid") {
                sslBadge = `<span class="monitor-type-badge" style="background: rgba(239, 68, 68, 0.15); border-color: var(--offline); color: var(--offline); font-size: 0.65rem;">SSL INVALID</span>`;
            } else {
                sslBadge = `<span class="monitor-type-badge" style="font-size: 0.65rem;">No SSL (HTTP)</span>`;
            }

            const latencyVal = web.response_time !== null ? `${Math.round(web.response_time)} ms` : "N/A";
            const codeVal = web.status_code !== null ? web.status_code : "FAIL";

            return `
                <div class="card ${statusClass}" draggable="true" data-id="${web.id}">
                    <div class="card-header" style="margin-bottom: 0.75rem;">
                        <div class="server-title-container">
                            <span class="server-name" style="font-size: 0.95rem;">${web.name}</span>
                            <a href="${web.url}" target="_blank" class="server-ip" style="text-decoration: underline; color: var(--accent); max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${web.url}</a>
                        </div>
                        <span class="status-badge ${statusClass}">
                            <span class="dot"></span> ${statusText}
                        </span>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.75rem; font-size: 0.8rem; background: rgba(255,255,255,0.02); padding: 0.5rem; border-radius: 6px; border: 1px solid var(--border-color);">
                        <div><strong>HTTP Code:</strong> <span style="color: ${isOnline ? 'var(--online)' : 'var(--offline)'}; font-weight: bold;">${codeVal}</span></div>
                        <div><strong>Latency:</strong> ${latencyVal}</div>
                    </div>

                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.75rem;">
                        <div>Last Check: ${web.last_checked ? parseUTC(web.last_checked).toLocaleTimeString() : "Never"}</div>
                        ${sslBadge}
                    </div>

                    ${web.error_message ? `
                    <div style="font-size: 0.7rem; color: var(--offline); background: rgba(239, 68, 68, 0.05); padding: 0.4rem; border-radius: 4px; border: 1px solid rgba(239, 68, 68, 0.15); margin-bottom: 0.75rem; max-height: 45px; overflow-y: auto; word-break: break-all;">
                        ${web.error_message}
                    </div>` : ""}

                    <div class="server-footer" style="margin-top: auto; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05); display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.7rem; border-color: var(--accent); color: var(--text-primary);" onclick="manageWebsiteNotifications(${web.id})">
                            🔔 Notifikasi
                        </button>
                        <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.7rem; border-color: rgba(239, 68, 68, 0.3); color: #ef4444; ${hideDeleteBtn}" onclick="deleteWebsite(${web.id})">
                            Hapus
                        </button>
                    </div>
                </div>
            `;
        }).join("");
    }

    // Delete Website
    window.deleteWebsite = async function(webId) {
        if (!confirm("Apakah Anda yakin ingin menghapus monitoring website ini?")) return;
        try {
            const res = await fetch(`/api/websites/${webId}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Gagal menghapus website");
            loadWebsites();
        } catch (error) {
            alert(error.message);
        }
    };

    // Drag and drop handler for Websites
    function setupWebDragAndDrop() {
        const container = document.getElementById("websites-container");
        if (!container) return;

        let draggedItem = null;

        container.ondragstart = (e) => {
            const card = e.target.closest('[draggable="true"]');
            if (card) {
                draggedItem = card;
                e.dataTransfer.effectAllowed = 'move';
                card.style.opacity = '0.5';
            }
        };

        container.ondragend = (e) => {
            const card = e.target.closest('[draggable="true"]');
            if (card) {
                card.style.opacity = '1';
            }
            draggedItem = null;
            container.querySelectorAll('[draggable="true"]').forEach(c => {
                c.style.border = '';
            });
        };

        container.ondragover = (e) => {
            e.preventDefault();
            const card = e.target.closest('[draggable="true"]');
            if (card && card !== draggedItem) {
                e.dataTransfer.dropEffect = 'move';
                card.style.border = '2px dashed var(--accent)';
            }
        };

        container.ondragleave = (e) => {
            const card = e.target.closest('[draggable="true"]');
            if (card && card !== draggedItem) {
                card.style.border = '';
            }
        };

        container.ondrop = (e) => {
            e.preventDefault();
            const card = e.target.closest('[draggable="true"]');
            if (card && card !== draggedItem && draggedItem) {
                card.style.border = '';
                
                const draggedId = parseInt(draggedItem.getAttribute('data-id'), 10);
                const targetId = parseInt(card.getAttribute('data-id'), 10);
                
                const draggedIndex = cachedWebsites.findIndex(s => s.id === draggedId);
                const targetIndex = cachedWebsites.findIndex(s => s.id === targetId);
                
                if (draggedIndex !== -1 && targetIndex !== -1) {
                    const [removed] = cachedWebsites.splice(draggedIndex, 1);
                    cachedWebsites.splice(targetIndex, 0, removed);
                    
                    const newOrder = cachedWebsites.map(s => s.id);
                    localStorage.setItem('sentinel360_website_order', JSON.stringify(newOrder));
                    
                    renderWebsites(cachedWebsites);
                    setupWebDragAndDrop();
                }
            }
        };
    }

    // Initial load and start interval polling
    loadServers();
    loadWebsites();
    loadAlerts();
    serverPollInterval = setInterval(loadServers, 5000);
    websitePollInterval = setInterval(loadWebsites, 5000);
    alertPollInterval = setInterval(loadAlerts, 5000);

    // Stop intervals when page changes (navigating away)
    window.addEventListener("beforeunload", () => {
        clearInterval(serverPollInterval);
        clearInterval(websitePollInterval);
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

    const deleteBtn = document.getElementById("delete-server-btn");
    if (deleteBtn && typeof USER_ROLE !== "undefined" && USER_ROLE === "view") {
        deleteBtn.style.display = "none";
    }

    async function loadServerNotificationGroups() {
        const container = document.getElementById("server-groups-checklist");
        if (!container) return;
        try {
            // Get active notifications of this server first
            const sRes = await fetch(`/api/servers/${serverId}`);
            if (!sRes.ok) throw new Error("Gagal mengambil info server.");
            const server = await sRes.json();
            const activeIds = (server.notifications || []).map(n => n.id);

            // Get all notification setups
            const res = await fetch("/api/notifications");
            if (!res.ok) throw new Error("Gagal mengambil data setup notifikasi.");
            const allConfigs = await res.json();

            if (allConfigs.length === 0) {
                container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.85rem; font-style: italic; margin: 0;">Belum ada setup notifikasi. Silakan buat di Dashboard -> Notifikasi.</p>';
            } else {
                container.innerHTML = allConfigs.map(c => `
                    <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; color: var(--text-primary); cursor: pointer; border: 1px solid var(--border-color); padding: 0.5rem; border-radius: 6px; background: rgba(255,255,255,0.01);">
                        <input type="checkbox" name="server_detail_group_id" value="${c.id}" ${activeIds.includes(c.id) ? 'checked' : ''}>
                        <strong>${c.name}</strong> (${c.type.toUpperCase()})
                    </label>
                `).join("");
            }
        } catch (error) {
            console.error("Error loading server notification configurations:", error);
        }
    }

    const saveServerGroupsBtn = document.getElementById("save-server-groups-btn");
    if (saveServerGroupsBtn) {
        saveServerGroupsBtn.addEventListener("click", async () => {
            const checkedBoxes = document.querySelectorAll('input[name="server_detail_group_id"]:checked');
            const notificationIds = Array.from(checkedBoxes).map(cb => parseInt(cb.value, 10));

            try {
                const res = await fetch(`/api/servers/${serverId}/notifications`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(notificationIds)
                });
                if (!res.ok) throw new Error("Gagal menyimpan pengaturan notifikasi.");

                alert("Pengaturan notifikasi berhasil disimpan!");
            } catch (error) {
                alert("Error: " + error.message);
            }
        });
    }

    async function loadServerDetails() {
        try {
            // Load Server Basic info
            const sRes = await fetch(`/api/servers/${serverId}`);
            if (sRes.status === 401) {
                window.location.href = "/login";
                return;
            }
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
            document.getElementById("detail-seen").textContent = server.last_seen ? parseUTC(server.last_seen).toLocaleString() : "Never";
            
            // Update RAM/Disk detailed metrics if available
            const ramContainer = document.getElementById("detail-ram-container");
            const diskContainer = document.getElementById("detail-disk-container");

            if (server.ram_total && server.ram_usage !== null) {
                const ramTotal = parseFloat(server.ram_total);
                const ramUsed = (parseFloat(server.ram_usage) / 100) * ramTotal;
                document.getElementById("detail-ram").innerHTML = `${ramUsed.toFixed(1)} GB / ${ramTotal.toFixed(1)} GB <span style="font-size: 0.8rem; color: var(--text-secondary); font-weight: normal;">(${Math.round(server.ram_usage)}%)</span>`;
                if (ramContainer) ramContainer.style.display = "flex";
            } else if (ramContainer) {
                ramContainer.style.display = "none";
            }

            if (server.disk_total && server.disk_usage !== null) {
                const diskTotal = parseFloat(server.disk_total);
                const diskUsed = (parseFloat(server.disk_usage) / 100) * diskTotal;
                document.getElementById("detail-disk").innerHTML = `${diskUsed.toFixed(1)} GB / ${diskTotal.toFixed(1)} GB <span style="font-size: 0.8rem; color: var(--text-secondary); font-weight: normal;">(${Math.round(server.disk_usage)}%)</span>`;
                if (diskContainer) diskContainer.style.display = "flex";
            } else if (diskContainer) {
                diskContainer.style.display = "none";
            }

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
            if (res.status === 401) {
                window.location.href = "/login";
                return;
            }
            if (!res.ok) throw new Error("Failed to fetch metrics");
            const metrics = await res.json();
            
            drawCharts(metrics);
        } catch (error) {
            console.error("Error loading metrics:", error);
        }
    }

    function drawCharts(metrics) {
        // Extract data lists
        const labels = metrics.map(m => parseUTC(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
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

    // Export CSV handler
    const exportCsvBtn = document.getElementById("export-csv-btn");
    if (exportCsvBtn) {
        exportCsvBtn.addEventListener("click", async () => {
            const selectHours = document.getElementById("range-select")?.value || 12;
            exportCsvBtn.disabled = true;
            const originalText = exportCsvBtn.innerHTML;
            exportCsvBtn.innerHTML = "Processing...";
            try {
                const res = await fetch(`/api/servers/${serverId}/metrics?hours=${selectHours}`);
                if (!res.ok) throw new Error("Gagal mengambil data monitoring");
                const metrics = await res.json();
                
                if (metrics.length === 0) {
                    alert("Tidak ada data monitoring untuk rentang waktu ini.");
                    return;
                }
                
                // Format CSV Content (with BOM for Excel compatibility)
                const headers = ["Waktu", "CPU Usage (%)", "RAM Usage (%)", "RAM Total (GB)", "Disk Usage (%)", "Disk Total (GB)", "Ping Latency (ms)", "Net RX (Kbps)", "Net TX (Kbps)"];
                const csvRows = [headers.join(",")];
                
                metrics.forEach(m => {
                    const timeStr = parseUTC(m.timestamp).toLocaleString();
                    const row = [
                        `"${timeStr}"`,
                        m.cpu_usage !== null ? m.cpu_usage.toFixed(1) : "",
                        m.ram_usage !== null ? m.ram_usage.toFixed(1) : "",
                        m.ram_total !== null ? m.ram_total.toFixed(1) : "",
                        m.disk_usage !== null ? m.disk_usage.toFixed(1) : "",
                        m.disk_total !== null ? m.disk_total.toFixed(1) : "",
                        m.latency !== null ? m.latency.toFixed(1) : "",
                        m.network_rx !== null ? m.network_rx.toFixed(1) : "",
                        m.network_tx !== null ? m.network_tx.toFixed(1) : ""
                    ];
                    csvRows.push(row.join(","));
                });
                
                const csvString = csvRows.join("\r\n");
                const blob = new Blob([csvString], { type: "text/csv;charset=utf-8;\uFEFF" });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.setAttribute("href", url);
                
                const serverName = document.getElementById("detail-name")?.textContent || "server";
                const cleanName = serverName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
                link.setAttribute("download", `monitoring_${cleanName}_${selectHours}j.csv`);
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(url);
            } catch (error) {
                alert("Error mengekspor data: " + error.message);
            } finally {
                exportCsvBtn.disabled = false;
                exportCsvBtn.innerHTML = originalText;
            }
        });
    }

    // Initial load and start poll
    loadServerDetails();
    loadMetrics();
    loadServerNotificationGroups();
    detailPollInterval = setInterval(() => {
        loadServerDetails();
        loadMetrics();
    }, 5000);

    window.addEventListener("beforeunload", () => {
        clearInterval(detailPollInterval);
    });
}
