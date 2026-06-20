// ============================================================
// PrismaX Extension - Configuration
// Built-in config + mergeConfig + user config loading
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    // Built-in default configuration
    const BUILTIN_CONFIG = {
        pushdeerKey: '',  // PushDeer Key, e.g. 'PDU12345'
    };

    function mergeConfig(base, override) {
        const output = { ...base };
        if (!override || typeof override !== 'object') return output;
        for (const [key, value] of Object.entries(override)) {
            if (value && typeof value === 'object' && !Array.isArray(value) &&
                base[key] && typeof base[key] === 'object' && !Array.isArray(base[key])) {
                output[key] = mergeConfig(base[key], value);
            } else {
                output[key] = value;
            }
        }
        return output;
    }

    // Default main automation config
    const DEFAULT_MAIN_CONFIG = {
        stuckToleranceMin: 300,
        stuckToleranceMax: 360,
        safeZoneRawLimit: 4,
        highRankStandbyThreshold: 100,
        highRankLoopInterval: 3000,
        highRankDomScanInterval: 7000,
        rankDropTolerance: 3,
        timerFreezeTimeout: 45 * 1000,
        clickDelayMin: 1000,
        clickDelayMax: 3000,
        minSessionTime: 40 * 1000,
        fallbackReloadTimeout: 5 * 60 * 1000,
        maxQueueTimeMin: 170,
        requeueDelayMs: 2 * 1000,

        morningEnabled: true,
        morningWindowStart: "08:01",
        morningWindowEnd: "08:06",
        morningRandomInsideWindow: true,
        morningIgnoreDone: false,
        morningWatchdogEnabled: true,
        morningWatchdogTimeout: 15 * 1000,
        morningWatchdogCheckInterval: 1000,

        armSwitchTask: {
            enabled: true,
            successThreshold: 6,
            robotAvatarXPath: '/html/body/div[1]/div/div[2]/div/div[2]/ul/li[3]',
            trainingGoldArmXPath: '/html/body/div[1]/div/div[3]/div[2]/div/div/div[2]/div[2]',
            arenaArmXPath: '/html/body/div[1]/div/div[3]/div[2]/div/div/div[2]/div[3]',
            morningReturnToGold: true,
            afterLeaveDelay: 1200,
            afterAvatarDelay: 1200,
            afterArenaDelay: 1500
        },

        commentTask: {
            enabled: true,
            windowStart: "00:00",
            windowEnd: "00:05",
            randomInsideWindow: true,
            commentCount: { min: 5, max: 5 },
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

        text: {
            enter: ["Enter Live Control", "Join Queue", "Enter Pool"],
            end: ["End Tele-Operation", "End Session"],
            queuing: ["Leave", "Waiting", "Position", "Queued"],
            liveChat: ["Live Chat", "Open Live Chat"],
            queue: ["Queue"],
            blacklist: ["Discord", "Twitter", "Telegram", "Docs", "Whitepaper", "Log", "Sign"]
        }
    };

    // Default controller config
    const DEFAULT_CONTROLLER_CONFIG = {
        updateInterval: 500,
        pushInterval: 500,
        standbyUpdateInterval: 3000,
        standbyPushInterval: 3000,
        standbyRankThreshold: 100,
        highRankStandbyThreshold: 100,
        standbyEnabled: true,
        bridgeUrl: 'http://127.0.0.1:5000',
        enablePush: true,
        enableLocalStorage: true,
        maxRetries: 3,
        titlePrefix: 'PrismaX',
        titleOperating: 'PrismaX - OPERATING',
        titleQueuing: 'PrismaX - QUEUING',
        titleStandby: 'PrismaX - STANDBY',
        consecutiveAnomalyThreshold: 2,
        enableAnomalyAutoLeave: true,
        anomalyCooldownMinutes: 60
    };

    // Load user config from chrome.storage.sync
    async function loadUserConfig() {
        try {
            const result = await chrome.storage.sync.get('userConfig');
            return result.userConfig || {};
        } catch (e) {
            console.error('[Config] Failed to load user config:', e);
            return {};
        }
    }

    // Build the complete config
    async function buildConfig() {
        const userConfig = await loadUserConfig();

        // Merge builtin with user overrides
        const mergedBuiltin = mergeConfig(BUILTIN_CONFIG, userConfig);

        // Build main config
        const mainConfig = mergeConfig(DEFAULT_MAIN_CONFIG, userConfig.main || {});

        // Build controller config
        const controllerConfig = mergeConfig(DEFAULT_CONTROLLER_CONFIG, userConfig.controller || {});

        // Build notifier config
        const notifierConfig = mergeConfig({
            type: userConfig.notifierType || 'pushdeer',
            pushdeer: {
                key: mergedBuiltin.pushdeerKey || userConfig.pushdeerKey || '',
                api: 'https://api2.pushdeer.com/message/push'
            },
            wecom: { webhook: (userConfig.notifier || {}).wecomWebhook || '' },
            serverchan: {
                key: (userConfig.notifier || {}).serverchanKey || '',
                api: 'https://sctapi.ftqq.com'
            },
            telegram: {
                botToken: (userConfig.notifier || {}).telegramBotToken || '',
                chatId: (userConfig.notifier || {}).telegramChatId || '',
                api: 'https://api.telegram.org'
            },
            cooldown: (userConfig.notifier || {}).cooldown || 60,
            debug: true
        }, userConfig.notifier || {});

        return {
            builtin: mergedBuiltin,
            main: mainConfig,
            controller: controllerConfig,
            notifier: notifierConfig
        };
    }

    PX.Config = {
        BUILTIN_CONFIG: BUILTIN_CONFIG,
        DEFAULT_MAIN_CONFIG: DEFAULT_MAIN_CONFIG,
        DEFAULT_CONTROLLER_CONFIG: DEFAULT_CONTROLLER_CONFIG,
        mergeConfig: mergeConfig,
        loadUserConfig: loadUserConfig,
        buildConfig: buildConfig
    };
})();
