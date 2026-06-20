// ============================================================
// PrismaX Extension - Popup
// Quick status display and controls
// ============================================================

const els = {
    statusDot: document.getElementById('status-dot'),
    statusText: document.getElementById('status-text'),
    mode: document.getElementById('mode'),
    count: document.getElementById('count'),
    anomaly: document.getElementById('anomaly'),
    bridge: document.getElementById('bridge'),
    notifierStat: document.getElementById('notifier-stat'),
    morningTask: document.getElementById('morning-task'),
    commentTask: document.getElementById('comment-task'),
    armTask: document.getElementById('arm-task'),
    btnToggle: document.getElementById('btn-toggle'),
    btnReset: document.getElementById('btn-reset'),
    btnTestNotify: document.getElementById('btn-test-notify'),
    btnTestBridge: document.getElementById('btn-test-bridge'),
    btnOptions: document.getElementById('btn-options'),
    btnOpen: document.getElementById('btn-open')
};

// Helper: send message to content script via service worker or direct
async function sendToContent(action, data) {
    try {
        // Try direct message to active tab first
        const tabs = await chrome.tabs.query({ url: 'https://app.prismax.ai/*', active: true });
        if (tabs.length > 0) {
            return await chrome.tabs.sendMessage(tabs[0].id, { action, ...(data || {}) });
        }
        // Fallback: any PrismaX tab
        const allTabs = await chrome.tabs.query({ url: 'https://app.prismax.ai/*' });
        if (allTabs.length > 0) {
            return await chrome.tabs.sendMessage(allTabs[0].id, { action, ...(data || {}) });
        }
        return { error: 'No PrismaX tab open' };
    } catch (e) {
        // Try via service worker relay
        try {
            return await chrome.runtime.sendMessage({ target: 'content', action, data });
        } catch (e2) {
            return { error: e.message };
        }
    }
}

// Refresh status display
async function refreshStatus() {
    const state = await sendToContent('getState');

    if (state && !state.error) {
        // Status
        const ctrl = state.controller || {};
        if (ctrl.isOperating) {
            els.statusDot.className = 'status-dot active';
            els.statusText.textContent = '⚡ 操作中';
            els.mode.textContent = 'OPERATING';
            els.mode.className = 'value highlight';
        } else if (ctrl.isQueuing) {
            const rank = ctrl.rank ? ` #${ctrl.rank}` : '';
            els.statusDot.className = 'status-dot standby';
            els.statusText.textContent = `🔄 排队中${rank}`;
            els.mode.textContent = 'QUEUING';
            els.mode.className = 'value';
        } else {
            els.statusDot.className = 'status-dot offline';
            els.statusText.textContent = '⏳ 等待中';
            els.mode.textContent = 'STANDBY';
            els.mode.className = 'value';
        }

        // Counts
        els.count.textContent = `${state.count || 0} 次`;
        els.anomaly.textContent = `${state.anomaly || 0} 次`;

        // Bridge
        els.bridge.textContent = ctrl.pushStatus || '--';
        els.bridge.className = (ctrl.pushStatus || '').includes('✅') ? 'value highlight' : 'value warn';

        // Notifier
        const n = state.notifier || {};
        els.notifierStat.textContent = `${n.type || '--'} (${n.totalSent || 0}/${(n.totalSent || 0) + (n.totalFailed || 0)})`;

        // Tasks
        els.morningTask.textContent = state.morningDone ? '✅ 完成' : '⏳ 待触发';
        els.morningTask.className = state.morningDone ? 'value highlight' : 'value';
        els.commentTask.textContent = state.commentTaskDone ? '✅ 完成' : '⏳ 待触发';
        els.commentTask.className = state.commentTaskDone ? 'value highlight' : 'value';
        els.armTask.textContent = state.armSwitchDone ? '✅ 完成' : '⏳ 待触发';
        els.armTask.className = state.armSwitchDone ? 'value highlight' : 'value';

        // Toggle button
        els.btnToggle.textContent = state.paused ? '恢复脚本' : '暂停脚本';
    } else {
        els.statusText.textContent = '❌ 未连接到 PrismaX';
        els.statusDot.className = 'status-dot offline';
    }
}

// Button handlers
els.btnToggle.addEventListener('click', async () => {
    const result = await sendToContent('togglePause');
    if (result && !result.error) {
        els.btnToggle.textContent = result.paused ? '恢复脚本' : '暂停脚本';
    }
    refreshStatus();
});

els.btnReset.addEventListener('click', async () => {
    if (confirm('确定要重置今日统计数据？')) {
        await sendToContent('resetStats');
        refreshStatus();
    }
});

els.btnTestNotify.addEventListener('click', async () => {
    await sendToContent('testNotification');
    els.btnTestNotify.textContent = '已发送 ✓';
    setTimeout(() => { els.btnTestNotify.textContent = '测试通知'; }, 2000);
});

els.btnTestBridge.addEventListener('click', async () => {
    await sendToContent('testConnection');
    els.btnTestBridge.textContent = '已测试 ✓';
    setTimeout(() => { els.btnTestBridge.textContent = '测试连接'; }, 2000);
});

els.btnOptions.addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
});

els.btnOpen.addEventListener('click', async () => {
    await chrome.runtime.sendMessage({ action: 'openPrismaX' });
    window.close();
});

// Initial load
refreshStatus();

// Auto-refresh every 2 seconds
setInterval(refreshStatus, 2000);
