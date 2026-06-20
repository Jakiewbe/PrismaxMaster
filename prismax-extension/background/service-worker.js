// ============================================================
// PrismaX Extension - Background Service Worker
// Alarm scheduling, tab management, message relay
// ============================================================

const ALARM_MORNING = 'morningCheck';
const ALARM_COMMENT = 'commentCheck';
const PRISMAX_URL = 'https://app.prismax.ai/';

// ============================================================
// Alarm scheduling
// ============================================================

function scheduleMorningAlarm() {
    const now = new Date();
    // Schedule for 7:59 AM (1 minute before the 08:01 window)
    const target = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 7, 59, 0);
    if (now >= target) {
        target.setDate(target.getDate() + 1);
    }

    chrome.alarms.create(ALARM_MORNING, {
        when: target.getTime(),
        periodInMinutes: 1440 // Daily
    });
    console.log('[SW] Morning alarm scheduled for:', target.toLocaleString());
}

function scheduleCommentAlarm() {
    const now = new Date();
    // Schedule for 23:59 (1 minute before the 00:00 window)
    const target = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 0);
    if (now >= target) {
        target.setDate(target.getDate() + 1);
    }

    chrome.alarms.create(ALARM_COMMENT, {
        when: target.getTime(),
        periodInMinutes: 1440 // Daily
    });
    console.log('[SW] Comment alarm scheduled for:', target.toLocaleString());
}

function rescheduleAllAlarms() {
    chrome.alarms.clearAll(() => {
        scheduleMorningAlarm();
        scheduleCommentAlarm();
    });
}

// ============================================================
// Tab management
// ============================================================

async function findOrCreatePrismaXTab() {
    const tabs = await chrome.tabs.query({ url: 'https://app.prismax.ai/*' });
    if (tabs.length > 0) {
        return tabs[0];
    }
    // Create a new background tab
    const tab = await chrome.tabs.create({ url: PRISMAX_URL, active: false });
    console.log('[SW] Created new PrismaX tab:', tab.id);
    return tab;
}

async function notifyContentScript(tabId, action) {
    try {
        const response = await chrome.tabs.sendMessage(tabId, { action });
        console.log(`[SW] Sent ${action} to tab ${tabId}, response:`, response);
        return true;
    } catch (e) {
        console.warn(`[SW] Failed to send ${action} to tab ${tabId}:`, e.message);
        return false;
    }
}

// ============================================================
// Alarm handler
// ============================================================

chrome.alarms.onAlarm.addListener(async (alarm) => {
    console.log('[SW] Alarm fired:', alarm.name);

    if (alarm.name === ALARM_MORNING) {
        await handleMorningAlarm();
    } else if (alarm.name === ALARM_COMMENT) {
        await handleCommentAlarm();
    }
});

async function handleMorningAlarm() {
    const tab = await findOrCreatePrismaXTab();
    const sent = await notifyContentScript(tab.id, 'MORNING_TRIGGER');

    if (!sent) {
        // Content script may not be loaded yet, reload the tab
        console.log('[SW] Reloading tab to ensure content script is loaded');
        await chrome.tabs.reload(tab.id);
        // Wait for load, then try again
        setTimeout(async () => {
            await notifyContentScript(tab.id, 'MORNING_TRIGGER');
        }, 5000);
    }

    // Reschedule for next day
    scheduleMorningAlarm();
}

async function handleCommentAlarm() {
    const tab = await findOrCreatePrismaXTab();
    const sent = await notifyContentScript(tab.id, 'COMMENT_TRIGGER');

    if (!sent) {
        console.log('[SW] Reloading tab to ensure content script is loaded');
        await chrome.tabs.reload(tab.id);
        setTimeout(async () => {
            await notifyContentScript(tab.id, 'COMMENT_TRIGGER');
        }, 5000);
    }

    // Reschedule for next day
    scheduleCommentAlarm();
}

// ============================================================
// Message relay (popup <-> content script)
// ============================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // Messages from popup that need to reach content script
    if (message.target === 'content') {
        (async () => {
            const tabs = await chrome.tabs.query({ url: 'https://app.prismax.ai/*' });
            if (tabs.length > 0) {
                try {
                    const response = await chrome.tabs.sendMessage(tabs[0].id, {
                        action: message.action,
                        ...(message.data || {})
                    });
                    sendResponse(response);
                } catch (e) {
                    sendResponse({ error: e.message });
                }
            } else {
                sendResponse({ error: 'No PrismaX tab open' });
            }
        })();
        return true; // Keep channel open for async
    }

    // Direct messages for service worker
    if (message.action === 'getTabStatus') {
        (async () => {
            const tabs = await chrome.tabs.query({ url: 'https://app.prismax.ai/*' });
            sendResponse({
                tabsOpen: tabs.length,
                activeTabId: tabs.length > 0 ? tabs[0].id : null
            });
        })();
        return true;
    }

    if (message.action === 'openPrismaX') {
        chrome.tabs.create({ url: PRISMAX_URL, active: true });
        sendResponse({ success: true });
        return false;
    }
});

// ============================================================
// Lifecycle
// ============================================================

chrome.runtime.onInstalled.addListener(() => {
    console.log('[SW] Extension installed');
    rescheduleAllAlarms();
});

chrome.runtime.onStartup.addListener(() => {
    console.log('[SW] Browser started');
    rescheduleAllAlarms();
});

console.log('[SW] Service worker initialized');
