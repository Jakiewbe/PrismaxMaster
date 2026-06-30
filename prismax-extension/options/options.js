// ============================================================
// PrismaX Extension - Options Page
// Full configuration management
// ============================================================

// Default values mapping
const DEFAULTS = {
    notifierType: 'pushdeer',
    pushdeerKey: '',
    wecomWebhook: '',
    serverchanKey: '',
    telegramBotToken: '',
    telegramChatId: '',
    notifyCooldown: 60,

    morningEnabled: 'true',
    morningWindowStart: '08:01',
    morningWindowEnd: '08:06',

    commentTaskEnabled: 'true',
    commentWindowStart: '00:00',
    commentWindowEnd: '00:05',
    commentCountMin: 5,
    commentCountMax: 5,

    consecutiveAnomalyThreshold: 2,
    anomalyCooldownMinutes: 60,
    minSessionTime: 40,
    stuckToleranceMin: 300,
    stuckToleranceMax: 360,
    safeZoneRawLimit: 4,
    standbyRankThreshold: 100,
    clickDelayMin: 1000,
    clickDelayMax: 3000,

    bridgeUrl: 'http://127.0.0.1:5000',
    enablePush: 'true',
    maxRetries: 3,

    armSwitchEnabled: 'true',
    armSuccessThreshold: 6,
    morningReturnToGold: 'true'
};

// Load saved config and populate form
async function loadConfig() {
    const result = await chrome.storage.sync.get('userConfig');
    const cfg = (result.userConfig && result.userConfig._raw) || {};

    for (const [key, defaultValue] of Object.entries(DEFAULTS)) {
        const el = document.getElementById(key);
        if (!el) continue;
        const val = cfg[key] !== undefined ? cfg[key] : defaultValue;
        el.value = val;
    }
}

// Collect form data into config object
function collectConfig() {
    const raw = {};
    for (const key of Object.keys(DEFAULTS)) {
        const el = document.getElementById(key);
        if (!el) continue;
        raw[key] = el.value;
    }

    // Build the structured config object
    return {
        _raw: raw, // Store raw values for round-tripping

        pushdeerKey: raw.pushdeerKey,
        notifierType: raw.notifierType,

        main: {
            morningEnabled: raw.morningEnabled === 'true',
            morningWindowStart: raw.morningWindowStart,
            morningWindowEnd: raw.morningWindowEnd,
            morningRandomInsideWindow: true,
            morningIgnoreDone: false,
            morningWatchdogEnabled: true,
            morningWatchdogTimeout: 15000,
            morningWatchdogCheckInterval: 1000,

            stuckToleranceMin: parseInt(raw.stuckToleranceMin, 10),
            stuckToleranceMax: parseInt(raw.stuckToleranceMax, 10),
            safeZoneRawLimit: parseInt(raw.safeZoneRawLimit, 10),
            highRankStandbyThreshold: parseInt(raw.standbyRankThreshold, 10),
            standbyRankThreshold: parseInt(raw.standbyRankThreshold, 10),
            rankDropTolerance: 3,
            timerFreezeTimeout: 45000,
            clickDelayMin: parseInt(raw.clickDelayMin, 10),
            clickDelayMax: parseInt(raw.clickDelayMax, 10),
            minSessionTime: parseInt(raw.minSessionTime, 10) * 1000,
            fallbackReloadTimeout: 300000,
            maxQueueTimeMin: 170,
            requeueDelayMs: 2000,

            commentTask: {
                enabled: raw.commentTaskEnabled === 'true',
                windowStart: raw.commentWindowStart,
                windowEnd: raw.commentWindowEnd,
                randomInsideWindow: true,
                commentCount: {
                    min: parseInt(raw.commentCountMin, 10),
                    max: parseInt(raw.commentCountMax, 10)
                },
                commentDelay: { min: 5000, max: 8000 },
                retryCount: 3,
                retryDelay: 2000,
                comments: [
                    "PrismaX demonstrates an exceptional integration of Web3 automation, intelligent execution logic, and user-centric design, making it one of the most forward-looking and practically useful AI agents in the decentralized ecosystem today.",
                    "What truly sets PrismaX apart is not only its technical robustness, but also its ability to translate complex on-chain operations into reliable, scalable, and fully autonomous decision-making workflows.",
                    "PrismaX is redefining how users interact with decentralized systems by combining strategic intelligence, execution efficiency, and a remarkably intuitive automation framework into a single coherent product.",
                    "In an ecosystem full of experimental tools, PrismaX stands out as a production-grade, mission-critical AI agent infrastructure that can genuinely support long-term, large-scale Web3 operations.",
                    "The architectural design of PrismaX reflects a deep understanding of both blockchain mechanics and real-world automation needs, resulting in a system that is powerful, flexible, and surprisingly easy to deploy.",
                    "By bridging intelligent agents with decentralized finance and on-chain execution, PrismaX is not merely a tool, but a foundational layer for the next generation of autonomous Web3 applications."
                ]
            },

            armSwitchTask: {
                enabled: raw.armSwitchEnabled === 'true',
                successThreshold: parseInt(raw.armSuccessThreshold, 10),
                robotAvatarXPath: '/html/body/div[1]/div/div[2]/div/div[2]/ul/li[3]',
                trainingGoldArmXPath: '/html/body/div[1]/div/div[3]/div[2]/div/div/div[2]/div[2]',
                arenaArmXPath: '/html/body/div[1]/div/div[3]/div[2]/div/div/div[2]/div[3]',
                morningReturnToGold: raw.morningReturnToGold === 'true',
                afterLeaveDelay: 1200,
                afterAvatarDelay: 1200,
                afterArenaDelay: 1500
            },

            text: {
                enter: ["Enter Live Control", "Join Queue", "Enter Pool", "Control Now"],
                end: ["End Tele-Operation", "End Session", "End Control", "Stop Validating"],
                queuing: ["Leave", "Leave Queue", "Waiting", "Position", "Queued", "In Queue"],
                liveChat: ["Live Chat", "Open Live Chat"],
                queue: ["Queue"],
                blacklist: ["Discord", "Twitter", "Telegram", "Docs", "Whitepaper", "Log", "Sign"]
            }
        },

        controller: {
            updateInterval: 500,
            pushInterval: 500,
            standbyUpdateInterval: 3000,
            standbyPushInterval: 3000,
            standbyRankThreshold: parseInt(raw.standbyRankThreshold, 10),
            highRankStandbyThreshold: parseInt(raw.standbyRankThreshold, 10),
            standbyEnabled: true,
            bridgeUrl: raw.bridgeUrl,
            enablePush: raw.enablePush === 'true',
            enableLocalStorage: true,
            maxRetries: parseInt(raw.maxRetries, 10),
            titlePrefix: 'PrismaX',
            titleOperating: 'PrismaX - OPERATING',
            titleQueuing: 'PrismaX - QUEUING',
            titleStandby: 'PrismaX - STANDBY',
            consecutiveAnomalyThreshold: parseInt(raw.consecutiveAnomalyThreshold, 10),
            enableAnomalyAutoLeave: true,
            anomalyCooldownMinutes: parseInt(raw.anomalyCooldownMinutes, 10)
        },

        notifier: {
            type: raw.notifierType,
            pushdeer: {
                key: raw.pushdeerKey,
                api: 'https://api2.pushdeer.com/message/push'
            },
            wecom: { webhook: raw.wecomWebhook },
            serverchan: {
                key: raw.serverchanKey,
                api: 'https://sctapi.ftqq.com'
            },
            telegram: {
                botToken: raw.telegramBotToken,
                chatId: raw.telegramChatId,
                api: 'https://api.telegram.org'
            },
            cooldown: parseInt(raw.notifyCooldown, 10),
            debug: true
        }
    };
}

// Save config
async function saveConfig(e) {
    e.preventDefault();
    const status = document.getElementById('save-status');
    try {
        const config = collectConfig();
        await chrome.storage.sync.set({ userConfig: config });
        status.className = 'success';
        status.textContent = '✅ 设置已保存！刷新 PrismaX 页面以应用新设置。';
        status.style.display = 'block';
        setTimeout(() => { status.style.display = 'none'; }, 4000);
    } catch (err) {
        status.className = 'error';
        status.textContent = '❌ 保存失败: ' + err.message;
        status.style.display = 'block';
    }
}

// Export config as JSON file
async function exportConfig() {
    const result = await chrome.storage.sync.get('userConfig');
    const json = JSON.stringify(result.userConfig || {}, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'prismax-config.json';
    a.click();
    URL.revokeObjectURL(url);
}

// Import config from JSON file
async function importConfig() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
            const text = await file.text();
            const config = JSON.parse(text);
            await chrome.storage.sync.set({ userConfig: config });
            const status = document.getElementById('save-status');
            status.className = 'success';
            status.textContent = '✅ 配置已导入！刷新页面以应用。';
            status.style.display = 'block';
            setTimeout(() => { status.style.display = 'none'; }, 3000);
            loadConfig();
        } catch (err) {
            const status = document.getElementById('save-status');
            status.className = 'error';
            status.textContent = '❌ 导入失败: ' + err.message;
            status.style.display = 'block';
        }
    };
    input.click();
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    document.getElementById('settings-form').addEventListener('submit', saveConfig);
    document.getElementById('btn-export').addEventListener('click', exportConfig);
    document.getElementById('btn-import').addEventListener('click', importConfig);
});

