let topoData = null;
let allSDNEvents = [];
let currentEventFilter = 'ALL';

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    fetchStatus();
    fetchTopology();
    fetchFirewallRules();
    fetchQoSMeters();
    fetchFlows();
    fetchSDNEvents();

    // Auto-refresh network telemetry every 2.5 seconds
    setInterval(() => {
        fetchStatus();
        fetchTopology();
        fetchSDNEvents();
        const activeTab = document.querySelector('.tab-pane.active');
        if (activeTab && activeTab.id === 'tab-flows') {
            fetchFlows();
        }
    }, 2500);
});

function initNavigation() {
    const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            const tabId = item.getAttribute('data-tab');
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            const activePane = document.getElementById(tabId);
            if (activePane) activePane.classList.add('active');

            if (tabId === 'tab-topology') {
                setTimeout(drawTopology, 50);
            } else if (tabId === 'tab-flows') {
                fetchFlows();
            } else if (tabId === 'tab-events') {
                fetchSDNEvents();
            } else if (tabId === 'tab-snapshots') {
                fetchSnapshots();
            }
        });
    });
}

async function fetchStatus() {
    try {
        const res = await fetch('/api/sdn/status');
        const data = await res.json();
        document.getElementById('val-switch-count').innerText = data.switch_count;
        document.getElementById('val-host-count').innerText = data.host_count;
        document.getElementById('val-rule-count').innerText = data.firewall_rules_count;
        document.getElementById('val-controller-mode').innerText = data.mode;
        const ind = document.getElementById('ind-controller');
        if (ind) {
            ind.className = data.ryu_online ? 'status-indicator online' : 'status-indicator offline';
        }
    } catch (e) {
        console.error('Lỗi tải status:', e);
    }
}

async function fetchTopology() {
    try {
        const res = await fetch('/api/sdn/topology');
        topoData = await res.json();
        drawTopology();
        renderLinksMatrix();
    } catch (e) {
        console.error('Lỗi tải topology:', e);
    }
}

function renderLinksMatrix() {
    const tbody = document.getElementById('links-table-body');
    const pillStatus = document.getElementById('val-links-status');
    const pillInd = document.getElementById('ind-links');
    if (!tbody || !topoData || !topoData.links) return;

    tbody.innerHTML = '';
    let downCount = 0;

    topoData.links.forEach(l => {
        const isDown = (l.status === 'DOWN');
        if (isDown) downCount++;

        const tr = document.createElement('tr');
        if (isDown) {
            tr.style.backgroundColor = 'rgba(239, 68, 68, 0.15)';
        }

        const badgeHtml = isDown
            ? `<span class="flow-badge badge-drop" style="font-weight:700; animation: blink 1s infinite;">🔴 ĐỨT CÁP / DOWN</span>`
            : `<span class="flow-badge badge-allow" style="font-weight:600;">🟢 HOẠT ĐỘNG (UP)</span>`;

        tr.innerHTML = `
            <td><strong style="color:${isDown ? '#f87171' : '#38bdf8'};">${l.src.toUpperCase()} ⟷ ${l.dst.toUpperCase()}</strong></td>
            <td><code>${l.src}-eth${l.src_port} (port ${l.src_port})</code></td>
            <td><code>${l.dst}-eth${l.dst_port} (port ${l.dst_port})</code></td>
            <td><span style="color:#94a3b8;">${l.speed || '1 Gbps'}</span> | <span style="color:#a855f7;">${l.latency || '0.15 ms'}</span></td>
            <td>${badgeHtml}</td>
        `;
        tbody.appendChild(tr);
    });

    if (pillStatus && pillInd) {
        if (downCount > 0) {
            pillStatus.innerText = `⚠️ ${downCount} đường truyền DOWN`;
            pillStatus.style.color = '#ef4444';
            pillInd.className = 'status-indicator offline';
        } else {
            pillStatus.innerText = 'Tất cả UP (3/3)';
            pillStatus.style.color = '#10b981';
            pillInd.className = 'status-indicator online';
        }
    }
}

function drawTopology() {
    const canvas = document.getElementById('topoCanvas');
    if (!canvas || !topoData) return;
    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Mininet Layout: 3 Switches in Mesh + 4 Hosts
    const coords = {
        's1': { x: canvas.width * 0.32, y: 160, type: 'switch', label: 's1 (Core Switch)' },
        's2': { x: canvas.width * 0.68, y: 160, type: 'switch', label: 's2 (Distribution)' },
        's3': { x: canvas.width * 0.5,  y: 290, type: 'switch', label: 's3 (Server Farm)' },
        'h1': { x: canvas.width * 0.15, y: 160, type: 'host', label: 'h1 (Client 10.0.0.1)' },
        'h2': { x: canvas.width * 0.85, y: 160, type: 'host', label: 'h2 (Client 10.0.0.2)' },
        'h3': { x: canvas.width * 0.35, y: 440, type: 'host', label: 'h3 (Web Server :80)' },
        'h4': { x: canvas.width * 0.65, y: 440, type: 'host', label: 'h4 (Win File Server :445)' }
    };

    // Draw Data Plane Trunk Links between Switches
    topoData.links.forEach(link => {
        const p1 = coords[link.src];
        const p2 = coords[link.dst];
        if (p1 && p2) {
            const isDown = (link.status === 'DOWN');
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);

            if (isDown) {
                ctx.setLineDash([8, 6]);
                ctx.lineWidth = 4;
                ctx.strokeStyle = '#ef4444';
            } else {
                ctx.setLineDash([]);
                ctx.lineWidth = 3;
                ctx.strokeStyle = '#3b82f6';
            }
            ctx.stroke();
            ctx.setLineDash([]); // Reset line dash

            // Draw link label at midpoint
            const midX = (p1.x + p2.x) / 2;
            const midY = (p1.y + p2.y) / 2;
            
            ctx.save();
            if (isDown) {
                // Red Warning Box on broken link
                ctx.fillStyle = '#7f1d1d';
                ctx.strokeStyle = '#ef4444';
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.roundRect ? ctx.roundRect(midX - 45, midY - 12, 90, 24, 6) : ctx.rect(midX - 45, midY - 12, 90, 24);
                ctx.fill();
                ctx.stroke();

                ctx.fillStyle = '#fef2f2';
                ctx.font = 'bold 11px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText('⚠️ LINK DOWN', midX, midY);
            } else {
                // Soft blue indicator
                ctx.fillStyle = '#0f172a';
                ctx.strokeStyle = '#3b82f6';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.roundRect ? ctx.roundRect(midX - 25, midY - 9, 50, 18, 4) : ctx.rect(midX - 25, midY - 9, 50, 18);
                ctx.fill();
                ctx.stroke();

                ctx.fillStyle = '#93c5fd';
                ctx.font = '10px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(link.speed || '1 Gbps', midX, midY);
            }
            ctx.restore();
        }
    });

    // Draw Access Links (Host to Switch)
    ctx.lineWidth = 2;
    topoData.hosts.forEach(host => {
        const hp = coords[host.id];
        const sp = coords[host.switch];
        if (hp && sp) {
            ctx.beginPath();
            ctx.moveTo(hp.x, hp.y);
            ctx.lineTo(sp.x, sp.y);
            ctx.strokeStyle = '#64748b';
            ctx.stroke();
        }
    });

    // Draw Nodes
    Object.keys(coords).forEach(key => {
        const node = coords[key];
        ctx.beginPath();
        if (node.type === 'switch') {
            ctx.arc(node.x, node.y, 24, 0, 2 * Math.PI);
            ctx.fillStyle = '#1e3a8a';
            ctx.fill();
            ctx.lineWidth = 3;
            ctx.strokeStyle = '#60a5fa';
            ctx.stroke();

            ctx.fillStyle = '#f8fafc';
            ctx.font = 'bold 12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(node.label, node.x, node.y + 38);
        } else {
            ctx.rect(node.x - 22, node.y - 14, 44, 28);
            ctx.fillStyle = key === 'h3' ? '#065f46' : (key === 'h4' ? '#1e3a8a' : '#334155');
            ctx.fill();
            ctx.lineWidth = 2;
            ctx.strokeStyle = key === 'h3' ? '#34d399' : (key === 'h4' ? '#38bdf8' : '#94a3b8');
            ctx.stroke();

            ctx.fillStyle = '#f8fafc';
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(node.label, node.x, node.y + 28);
        }
    });
}

// SDN Events & Network State Change Handlers
async function fetchSDNEvents() {
    try {
        const res = await fetch('/api/sdn/events');
        allSDNEvents = await res.json();
        updateEventCounters();
        renderSDNEvents();
    } catch (e) {
        console.error('Lỗi tải SDN Events:', e);
    }
}

function updateEventCounters() {
    const dangerCount = allSDNEvents.filter(e => (e.level || '').toUpperCase() === 'DANGER').length;
    const successCount = allSDNEvents.filter(e => (e.level || '').toUpperCase() === 'SUCCESS').length;
    const configCount = allSDNEvents.filter(e => {
        const lvl = (e.level || '').toUpperCase();
        return lvl === 'INFO' || lvl === 'WARNING';
    }).length;

    const elAll = document.getElementById('count-all');
    const elDanger = document.getElementById('count-danger');
    const elSuccess = document.getElementById('count-success');
    const elConfig = document.getElementById('count-config');

    if (elAll) elAll.innerText = allSDNEvents.length;
    if (elDanger) elDanger.innerText = dangerCount;
    if (elSuccess) elSuccess.innerText = successCount;
    if (elConfig) elConfig.innerText = configCount;

    // Badge in sidebar navigation
    const badge = document.getElementById('badge-events-count');
    if (badge) {
        if (dangerCount > 0) {
            badge.style.display = 'inline-block';
            badge.style.backgroundColor = '#ef4444';
            badge.innerText = `${dangerCount} Lỗi`;
        } else if (allSDNEvents.length > 0) {
            badge.style.display = 'inline-block';
            badge.style.backgroundColor = '#3b82f6';
            badge.innerText = `${allSDNEvents.length}`;
        } else {
            badge.style.display = 'none';
        }
    }
}

function filterEvents(type) {
    currentEventFilter = type;
    
    // Update active button state
    ['all', 'danger', 'success', 'config'].forEach(k => {
        const btn = document.getElementById(`filter-${k}`);
        if (btn) {
            if (k.toUpperCase() === type) {
                btn.classList.add('active-filter');
                btn.style.boxShadow = '0 0 0 2px #3b82f6';
            } else {
                btn.classList.remove('active-filter');
                btn.style.boxShadow = 'none';
            }
        }
    });

    renderSDNEvents();
}

function renderSDNEvents() {
    const tbody = document.getElementById('events-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    let filtered = allSDNEvents;
    if (currentEventFilter === 'DANGER') {
        filtered = allSDNEvents.filter(e => (e.level || '').toUpperCase() === 'DANGER');
    } else if (currentEventFilter === 'SUCCESS') {
        filtered = allSDNEvents.filter(e => (e.level || '').toUpperCase() === 'SUCCESS');
    } else if (currentEventFilter === 'CONFIG') {
        filtered = allSDNEvents.filter(e => {
            const lvl = (e.level || '').toUpperCase();
            return lvl === 'INFO' || lvl === 'WARNING';
        });
    }

    if (!filtered || filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#64748b; padding:28px;">Không có sự kiện hoặc cảnh báo nào trong danh mục này</td></tr>`;
        return;
    }

    filtered.forEach(ev => {
        const tr = document.createElement('tr');
        
        const lvl = (ev.level || '').toUpperCase();
        let badgeClass = 'badge-allow';
        let levelLabel = 'INFO';
        let rowBg = 'transparent';

        if (lvl === 'DANGER') {
            badgeClass = 'badge-drop';
            levelLabel = '🚨 CẢNH BÁO';
            rowBg = 'rgba(239, 68, 68, 0.08)';
        } else if (lvl === 'SUCCESS') {
            badgeClass = 'badge-allow';
            levelLabel = '🟢 PHỤC HỒI';
            rowBg = 'rgba(16, 185, 129, 0.06)';
        } else if (lvl === 'WARNING') {
            badgeClass = 'badge-meter';
            levelLabel = '⚡ CẢNH BÁO / CẤU HÌNH';
        } else {
            levelLabel = 'ℹ️ THÔNG TIN';
        }

        tr.style.backgroundColor = rowBg;

        const swLabel = ev.switch ? `<span class="flow-badge" style="background:#0f172a; color:#38bdf8; border:1px solid #0284c7;">${ev.switch.toUpperCase()}</span>` : `<span style="color:#94a3b8;">Hệ thống</span>`;

        tr.innerHTML = `
            <td style="color:#94a3b8; font-family:monospace; font-size:0.85rem;">${ev.timestamp || 'N/A'}</td>
            <td><span class="flow-badge ${badgeClass}">${ev.type || 'EVENT'}</span></td>
            <td>${swLabel}</td>
            <td style="color:#f8fafc; font-size:0.9rem;">${ev.detail || ev.message || ''}</td>
            <td><strong style="font-size:0.8rem; color:${lvl === 'DANGER' ? '#f87171' : (lvl === 'SUCCESS' ? '#34d399' : '#38bdf8')}">${levelLabel}</strong></td>
        `;
        tbody.appendChild(tr);
    });
}

async function clearSDNEvents() {
    if (!confirm('Bạn có chắc muốn xóa toàn bộ lịch sử biến động mạng và cảnh báo?')) return;
    try {
        await fetch('/api/sdn/events', { method: 'DELETE' });
        await fetchSDNEvents();
    } catch (e) {
        alert('Lỗi xóa events: ' + e);
    }
}

// Firewall Management
async function fetchFirewallRules() {
    try {
        const res = await fetch('/api/sdn/firewall');
        const rules = await res.json();
        const tbody = document.getElementById('fw-table-body');
        tbody.innerHTML = '';
        rules.forEach(r => {
            const tr = document.createElement('tr');
            const badgeClass = r.action === 'DROP' ? 'badge-drop' : 'badge-allow';
            tr.innerHTML = `
                <td>#${r.id}</td>
                <td>Switch s${r.dpid}</td>
                <td><code>${r.src_ip || '*'}</code></td>
                <td><code>${r.dst_ip || '*'}</code></td>
                <td>${r.proto}</td>
                <td>${r.dst_port || '*'}</td>
                <td><span class="flow-badge ${badgeClass}">${r.action}</span></td>
                <td>${r.description}</td>
                <td><button class="btn btn-secondary btn-sm" onclick="deleteFirewallRule(${r.id})">Xóa</button></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Lỗi tải firewall:', e);
    }
}

async function handleCreateFirewallRule(e) {
    e.preventDefault();
    const payload = {
        dpid: parseInt(document.getElementById('fw-dpid').value),
        src_ip: document.getElementById('fw-src-ip').value.trim(),
        dst_ip: document.getElementById('fw-dst-ip').value.trim(),
        proto: document.getElementById('fw-proto').value,
        dst_port: document.getElementById('fw-port').value ? parseInt(document.getElementById('fw-port').value) : null,
        action: document.getElementById('fw-action').value
    };
    try {
        const res = await fetch('/api/sdn/firewall', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            fetchFirewallRules();
            fetchStatus();
            alert('Đã đẩy Flow-Mod (OpenFlow 1.3) xuống Switch Mininet thành công!');
        }
    } catch (err) {
        alert('Lỗi: ' + err);
    }
}

async function deleteFirewallRule(id) {
    if (!confirm('Bạn có chắc muốn gỡ bỏ quy tắc này khỏi Switch?')) return;
    await fetch(`/api/sdn/firewall/${id}`, { method: 'DELETE' });
    fetchFirewallRules();
    fetchStatus();
}

// QoS Meters
async function fetchQoSMeters() {
    try {
        const res = await fetch('/api/sdn/qos');
        const meters = await res.json();
        const tbody = document.getElementById('qos-table-body');
        tbody.innerHTML = '';
        meters.forEach(m => {
            const tr = document.createElement('tr');
            const srcDisplay = m.src_ip ? `<code>${m.src_ip}</code>` : `<span style="color:#94a3b8;">*</span>`;
            const dstDisplay = m.dst_ip ? `<code>${m.dst_ip}</code>` : `<span style="color:#94a3b8;">*</span>`;
            tr.innerHTML = `
                <td>#${m.meter_id}</td>
                <td>Switch s${m.dpid}</td>
                <td><span class="flow-badge badge-meter">${m.rate_kbps} Kbps</span></td>
                <td>${srcDisplay}</td>
                <td>${dstDisplay}</td>
                <td>${m.description || m.target}</td>
                <td>${m.created_at}</td>
                <td><button class="btn btn-secondary btn-sm" onclick="deleteQoSMeter(${m.meter_id})">Xóa</button></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Lỗi tải QoS:', e);
    }
}

async function handleCreateQoSMeter(e) {
    e.preventDefault();
    const srcIp = document.getElementById('qos-src-ip').value.trim();
    const dstIp = document.getElementById('qos-dst-ip').value.trim();
    const dpid = parseInt(document.getElementById('qos-dpid').value);
    const rate = parseInt(document.getElementById('qos-rate').value) || 1000;

    const payload = {
        dpid: dpid,
        src_ip: srcIp,
        dst_ip: dstIp,
        rate_kbps: rate
    };
    try {
        const res = await fetch('/api/sdn/qos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            fetchQoSMeters();
            fetchStatus();
            fetchFlows();
            const targetLabel = (srcIp || dstIp) ? `${srcIp || '*'} ➔ ${dstIp || '*'}` : 'Tất cả traffic';
            alert(`Đã thiết lập QoS Meter Table (${targetLabel} - ${rate} Kbps) trên Switch s${dpid} thành công!`);
        }
    } catch (err) {
        alert('Lỗi: ' + err);
    }
}

async function deleteQoSMeter(id) {
    await fetch(`/api/sdn/qos/${id}`, { method: 'DELETE' });
    fetchQoSMeters();
    fetchStatus();
}

// Flow Tables
async function fetchFlows() {
    try {
        const swSelect = document.getElementById('flow-switch-select');
        const dpid = swSelect ? swSelect.value : 'all';
        const res = await fetch(`/api/sdn/flows?dpid=${dpid}`);
        const flows = await res.json();
        const tbody = document.getElementById('flows-table-body');
        tbody.innerHTML = '';

        if (!flows || !Array.isArray(flows) || flows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#64748b; padding:24px;">Chưa có flow nào trên switch đã chọn</td></tr>';
            return;
        }

        flows.forEach(f => {
            const tr = document.createElement('tr');
            
            // Format Switch name
            const swLabel = f.switch || (f.dpid ? `s${f.dpid}` : 's1');
            const swBadge = `<span class="flow-badge" style="background:#0f172a; color:#38bdf8; border:1px solid rgba(56,189,248,0.4);">${swLabel.toUpperCase()}</span>`;

            // Format Priority & Type
            let prioBadge = `<strong style="color:#cbd5e1;">${f.priority}</strong>`;
            if (f.priority >= 1000) {
                prioBadge = `<span class="flow-badge badge-drop">${f.priority} (Firewall)</span>`;
            } else if (f.priority === 0) {
                prioBadge = `<span class="flow-badge" style="background:#1e293b; color:#94a3b8; border:1px solid #334155;">0 (Table-Miss)</span>`;
            } else if (f.priority === 10) {
                prioBadge = `<span class="flow-badge badge-allow">${f.priority} (L2 Wire)</span>`;
            } else if (f.priority === 500) {
                prioBadge = `<span class="flow-badge badge-meter">${f.priority} (QoS)</span>`;
            }

            // Format Match Fields
            let matchHtml = '';
            const m = f.match || {};
            const keys = Object.keys(m);
            if (keys.length === 0 || f.priority === 0) {
                matchHtml = `<span style="color:#94a3b8; font-style:italic;">★ Khớp mọi gói tin (Match Any)</span>`;
            } else {
                let parts = [];
                if (m.nw_src || m.ipv4_src) parts.push(`<span style="color:#38bdf8;">Src:</span> <code>${m.nw_src || m.ipv4_src}</code>`);
                if (m.nw_dst || m.ipv4_dst) parts.push(`<span style="color:#a855f7;">Dst:</span> <code>${m.nw_dst || m.ipv4_dst}</code>`);
                if (m.in_port) parts.push(`<span style="color:#94a3b8;">In-Port:</span> <code>${m.in_port}</code>`);
                if (m.eth_dst) parts.push(`<span style="color:#cbd5e1;">Eth-Dst:</span> <code>${m.eth_dst}</code>`);
                if (m.ip_proto) {
                    const pName = m.ip_proto === 6 ? 'TCP' : (m.ip_proto === 1 ? 'ICMP' : (m.ip_proto === 17 ? 'UDP' : m.ip_proto));
                    parts.push(`<span style="color:#f59e0b;">Proto:</span> <code>${pName}</code>`);
                }
                if (m.tcp_dst) parts.push(`<span style="color:#f43f5e;">Port:</span> <code>${m.tcp_dst}</code>`);
                matchHtml = parts.length > 0 ? parts.join(' &nbsp;|&nbsp; ') : `<code>${JSON.stringify(m)}</code>`;
            }

            // Format Action
            let actionHtml = '';
            const actUpper = String(f.action || '').toUpperCase();
            if (actUpper === 'DROP' || actUpper === '') {
                actionHtml = `<span class="flow-badge badge-drop">DROP (HỦY BỎ)</span>`;
            } else if (actUpper.includes('CONTROLLER')) {
                actionHtml = `<span class="flow-badge" style="background:rgba(59,130,246,0.2); color:#60a5fa; border:1px solid #3b82f6;">GỬI LÊN CONTROLLER</span>`;
            } else if (actUpper.includes('NORMAL')) {
                actionHtml = `<span class="flow-badge badge-allow">FORWARD L2 (NORMAL)</span>`;
            } else {
                actionHtml = `<span class="flow-badge badge-allow">${f.action}</span>`;
            }

            tr.innerHTML = `
                <td>${swBadge}</td>
                <td>Table ${f.table_id}</td>
                <td>${prioBadge}</td>
                <td>${matchHtml}</td>
                <td>${actionHtml}</td>
                <td><strong style="color:#f8fafc;">${f.packets}</strong></td>
                <td>${f.bytes.toLocaleString()} B</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Lỗi tải flows:', e);
    }
}

// AI Copilot
const aiRulesStore = {};

async function handleAIChat(e) {
    e.preventDefault();
    const input = document.getElementById('ai-input');
    const text = input.value.trim();
    if (!text) return;

    const chatBox = document.getElementById('chat-messages');
    chatBox.innerHTML += `<div class="msg msg-user">${text}</div>`;
    input.value = '';
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const res = await fetch('/api/ai/copilot', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: text })
        });
        const data = await res.json();
        if (data.parsed) {
            const p = data.parsed;
            const ruleId = 'airule_' + Math.random().toString(36).substr(2, 9);
            aiRulesStore[ruleId] = p;

            let detail = `<p>🤖 <strong>${p.explanation || 'Đã phân tích ý định thành công'}</strong></p>`;
            detail += `<pre style="background:#020617; color:#38bdf8; padding:10px; border-radius:6px; font-size:0.8rem; overflow-x:auto; border:1px solid #1e293b;">${JSON.stringify(p, null, 2)}</pre>`;
            
            if (p.intent === 'FIREWALL_DROP' || p.action === 'DROP' || p.intent === 'FIREWALL_ALLOW') {
                detail += `<button id="btn-${ruleId}" class="btn btn-primary btn-sm" onclick="applyAIFirewallById('${ruleId}')" style="margin-top:8px; cursor:pointer;">🛡️ Áp Dụng Luật Xuống Switch Mininet</button>`;
            } else if (p.intent === 'QOS_LIMIT') {
                detail += `<button id="btn-${ruleId}" class="btn btn-primary btn-sm" onclick="applyAIQoSById('${ruleId}')" style="margin-top:8px; cursor:pointer;">⚡ Áp Dụng Bóp Băng Thông Xuống Switch Mininet</button>`;
            }
            chatBox.innerHTML += `<div class="msg msg-bot">${detail}</div>`;
        } else {
            chatBox.innerHTML += `<div class="msg msg-bot">${data.ai_raw || 'Không thể nhận diện ý định'}</div>`;
        }
        chatBox.scrollTop = chatBox.scrollHeight;
    } catch (err) {
        chatBox.innerHTML += `<div class="msg msg-bot" style="color:#f87171;">Lỗi gọi AI: ${err}</div>`;
    }
}

async function applyAIFirewallById(ruleId) {
    const ruleObj = aiRulesStore[ruleId];
    if (!ruleObj) return;
    const btn = document.getElementById('btn-' + ruleId);
    if (btn) {
        btn.disabled = true;
        btn.innerText = '⏳ Đang nạp rule xuống Switch...';
    }
    await applyAIFirewallRule(ruleObj);
    if (btn) {
        btn.innerText = '✅ Đã nạp thành công xuống Switch!';
        btn.style.background = '#059669';
    }
}

async function applyAIQoSById(ruleId) {
    const ruleObj = aiRulesStore[ruleId];
    if (!ruleObj) return;
    const btn = document.getElementById('btn-' + ruleId);
    if (btn) {
        btn.disabled = true;
        btn.innerText = '⏳ Đang thiết lập QoS...';
    }
    await applyAIQoSMeter(ruleObj);
    if (btn) {
        btn.innerText = '✅ Đã thiết lập QoS thành công!';
        btn.style.background = '#059669';
    }
}

async function applyAIFirewallRule(ruleObj) {
    const payload = {
        dpid: ruleObj.target_switch || 1,
        src_ip: ruleObj.match?.ipv4_src || '',
        dst_ip: ruleObj.match?.ipv4_dst || '',
        proto: ruleObj.match?.ip_proto === 6 ? 'TCP' : (ruleObj.match?.ip_proto === 1 ? 'ICMP' : 'ANY'),
        dst_port: ruleObj.match?.tcp_dst || null,
        action: ruleObj.action || 'DROP',
        description: ruleObj.explanation || 'Rule sinh bởi AI Copilot cho Mininet'
    };
    try {
        const res = await fetch('/api/sdn/firewall', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            fetchFirewallRules();
            fetchStatus();
            fetchFlows();
            alert(`✅ Đã áp dụng thành công luật ${payload.action} (${payload.src_ip} -> ${payload.dst_ip}) xuống Switch s${payload.dpid}!`);
        }
    } catch (e) {
        alert('Lỗi áp dụng rule: ' + e);
    }
}

async function applyAIQoSMeter(ruleObj) {
    const srcIp = ruleObj.src_ip || ruleObj.match?.ipv4_src || '';
    const dstIp = ruleObj.dst_ip || ruleObj.match?.ipv4_dst || '';
    const payload = {
        dpid: ruleObj.target_switch || 2,
        src_ip: srcIp,
        dst_ip: dstIp,
        target: ruleObj.target || (srcIp || dstIp ? `${srcIp || '*'} ➔ ${dstIp || '*'}` : 'Traffic'),
        rate_kbps: ruleObj.rate_kbps || 1000,
        burst_size: 500,
        description: ruleObj.explanation || 'Giới hạn băng thông sinh bởi AI'
    };
    try {
        const res = await fetch('/api/sdn/qos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            fetchQoSMeters();
            fetchStatus();
            fetchFlows();
            alert(`✅ Đã thiết lập QoS (${payload.target} - ${payload.rate_kbps} Kbps) trên Switch s${payload.dpid}!`);
        }
    } catch (e) {
        alert('Lỗi áp dụng QoS: ' + e);
    }
}

function quickSendAI(text) {
    const input = document.getElementById('ai-input');
    if (input) {
        input.value = text;
        const form = input.closest('form');
        if (form) {
            form.dispatchEvent(new Event('submit', { cancelable: true }));
        }
    }
}

// ==============================================================================
// SNAPSHOT & 1-CLICK ROLLBACK MANAGEMENT FRONTEND
// ==============================================================================

let currentSnapshots = [];
let selectedSnapshotId = null;
let selectedSnapshotData = null;

async function fetchSnapshots() {
    try {
        const res = await fetch('/api/sdn/snapshots');
        currentSnapshots = await res.json();
        renderSnapshotList();
        
        // Tự động chọn snapshot đầu tiên nếu chưa chọn bản nào
        if (currentSnapshots.length > 0 && !selectedSnapshotId) {
            selectSnapshot(currentSnapshots[0].id);
        }
    } catch (e) {
        console.error('Lỗi tải danh sách snapshots:', e);
    }
}

function renderSnapshotList() {
    const container = document.getElementById('snapshot-list-container');
    const badgeCount = document.getElementById('snapshot-count-badge');
    if (!container) return;

    if (badgeCount) {
        badgeCount.innerText = `${currentSnapshots.length} bản`;
    }

    if (!currentSnapshots || currentSnapshots.length === 0) {
        container.innerHTML = '<div style="text-align:center; padding:30px; color:#64748b;">Chưa có bản snapshot nào. Hãy bấm "Tạo Snapshot Mới"!</div>';
        return;
    }

    container.innerHTML = '';
    currentSnapshots.forEach(snap => {
        const item = document.createElement('div');
        item.className = 'snapshot-item' + (snap.id === selectedSnapshotId ? ' active' : '');
        item.onclick = () => selectSnapshot(snap.id);

        const autoBadge = snap.is_auto 
            ? '<span class="mininet-badge" style="background:#f59e0b; font-size:0.65rem; margin-left:6px;">AUTO</span>' 
            : '';

        item.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <div class="snapshot-name">${snap.name} ${autoBadge}</div>
                    <div class="snapshot-date">🕒 ${snap.created_at || 'N/A'}</div>
                </div>
            </div>
            <div style="margin-top:6px; display:flex; gap:6px; font-size:0.75rem;">
                <span class="flow-badge badge-allow" style="padding:1px 6px;">${snap.firewall_count} FW</span>
                <span class="flow-badge badge-meter" style="padding:1px 6px;">${snap.qos_count} QoS</span>
            </div>
            ${snap.description ? `<div style="font-size:0.75rem; color:#94a3b8; margin-top:4px; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">${snap.description}</div>` : ''}
        `;
        container.appendChild(item);
    });
}

async function selectSnapshot(id) {
    selectedSnapshotId = id;
    renderSnapshotList();

    const nameEl = document.getElementById('inspector-snap-name');
    const timeEl = document.getElementById('inspector-snap-time');
    const jsonView = document.getElementById('snapshot-json-view');
    const btnRestore = document.getElementById('btn-restore-snap');
    const btnDownload = document.getElementById('btn-download-snap');
    const btnDelete = document.getElementById('btn-delete-snap');
    const metaFw = document.getElementById('meta-snap-fw');
    const metaQos = document.getElementById('meta-snap-qos');

    if (jsonView) jsonView.innerText = 'Đang đọc nội dung file sao lưu...';

    try {
        const res = await fetch(`/api/sdn/snapshots/${id}`);
        if (!res.ok) throw new Error('Không tìm thấy snapshot');
        selectedSnapshotData = await res.json();

        if (nameEl) nameEl.innerText = selectedSnapshotData.name || id;
        if (timeEl) timeEl.innerText = `ID: ${id} • Tạo lúc: ${selectedSnapshotData.created_at || 'N/A'}`;
        if (metaFw) metaFw.innerText = (selectedSnapshotData.firewall_rules || []).length;
        if (metaQos) metaQos.innerText = (selectedSnapshotData.qos_meters || []).length;

        if (jsonView) {
            jsonView.innerText = JSON.stringify(selectedSnapshotData, null, 2);
        }

        if (btnRestore) btnRestore.disabled = false;
        if (btnDownload) btnDownload.disabled = false;
        if (btnDelete) btnDelete.disabled = false;
    } catch (e) {
        if (jsonView) jsonView.innerText = 'Lỗi tải chi tiết snapshot: ' + e;
    }
}

function openCreateSnapshotModal() {
    const modal = document.getElementById('modal-create-snapshot');
    const inputName = document.getElementById('input-snap-name');
    const inputDesc = document.getElementById('input-snap-desc');
    if (inputName) inputName.value = `Snapshot_${new Date().toLocaleTimeString('vi-VN').replace(/:/g, '')}`;
    if (inputDesc) inputDesc.value = 'Sao lưu thủ công trạng thái mạng';
    if (modal) modal.classList.add('active');
}

function closeCreateSnapshotModal() {
    const modal = document.getElementById('modal-create-snapshot');
    if (modal) modal.classList.remove('active');
}

async function handleCreateSnapshotSubmit(e) {
    e.preventDefault();
    const name = document.getElementById('input-snap-name').value.trim();
    const desc = document.getElementById('input-snap-desc').value.trim();

    try {
        const res = await fetch('/api/sdn/snapshots', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, description: desc })
        });
        const data = await res.json();
        closeCreateSnapshotModal();
        if (res.ok) {
            alert(`✅ Đã chụp Snapshot '${name}' thành công!`);
            await fetchSnapshots();
            if (data.snapshot) {
                selectSnapshot(data.snapshot.id);
            }
        }
    } catch (err) {
        alert('Lỗi tạo snapshot: ' + err);
    }
}

async function restoreCurrentSnapshot() {
    if (!selectedSnapshotId || !selectedSnapshotData) return;
    const snapName = selectedSnapshotData.name || selectedSnapshotId;
    const confirmed = confirm(`⚠️ CẢNH BÁO 1-CLICK ROLLBACK:\nBạn có chắc chắn muốn khôi phục mạng về bản sao lưu '${snapName}'?\n\nToàn bộ Flow Tables và Meter hiện tại sẽ được hoàn nguyên về đúng cấu hình này.`);
    if (!confirmed) return;

    const btn = document.getElementById('btn-restore-snap');
    if (btn) {
        btn.disabled = true;
        btn.innerText = '⏳ Đang hoàn nguyên mạng...';
    }

    try {
        const res = await fetch(`/api/sdn/snapshots/${selectedSnapshotId}/restore`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            alert(`🎉 THÀNH CÔNG:\n${data.message}\n- Đã khôi phục ${data.restored_firewall} luật Firewall\n- Đã khôi phục ${data.restored_qos} cấu hình QoS`);
            // Làm mới toàn bộ dữ liệu trên Dashboard
            fetchStatus();
            fetchTopology();
            fetchFirewallRules();
            fetchQoSMeters();
            fetchFlows();
            fetchSDNEvents();
        } else {
            alert('Lỗi khôi phục: ' + (data.detail || data.message));
        }
    } catch (e) {
        alert('Lỗi kết nối khi restore: ' + e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = '⚡ 1-Click Rollback';
        }
    }
}

function downloadCurrentSnapshot() {
    if (!selectedSnapshotId) return;
    window.open(`/api/sdn/snapshots/${selectedSnapshotId}/download`, '_blank');
}

async function deleteCurrentSnapshot() {
    if (!selectedSnapshotId) return;
    if (!confirm('Bạn có chắc chắn muốn xóa bản sao lưu này? Hành động này không thể hoàn tác.')) return;

    try {
        const res = await fetch(`/api/sdn/snapshots/${selectedSnapshotId}`, { method: 'DELETE' });
        if (res.ok) {
            alert('Đã xóa bản snapshot thành công.');
            selectedSnapshotId = null;
            selectedSnapshotData = null;
            document.getElementById('inspector-snap-name').innerText = 'Chọn một bản sao lưu';
            document.getElementById('inspector-snap-time').innerText = '';
            document.getElementById('snapshot-json-view').innerText = 'Vui lòng chọn một bản snapshot ở danh sách bên trái.';
            document.getElementById('btn-restore-snap').disabled = true;
            document.getElementById('btn-download-snap').disabled = true;
            document.getElementById('btn-delete-snap').disabled = true;
            await fetchSnapshots();
        }
    } catch (e) {
        alert('Lỗi xóa snapshot: ' + e);
    }
}

