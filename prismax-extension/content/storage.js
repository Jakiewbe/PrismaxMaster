// ============================================================
// PrismaX Extension - Storage (chrome.storage.local wrapper)
// Memory-cached async wrapper with synchronous read API
// Replaces the original localStorage-based Storage object
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    // Storage keys (matching original naming but without 'p_' prefix)
    const KEYS = {
        COUNT: 'count',
        DATE: 'date',
        MORNING_TARGET: 'morningTargetTs',
        ANOMALY_COUNT: 'anomalyCount',
        CONSECUTIVE_ANOMALIES: 'consecutiveAnomalies',
        ANOMALY_COOLDOWN: 'anomalyCooldown',
        COMMENT_TASK_DONE: 'commentTaskDone',
        COMMENT_TASK_TARGET: 'commentTargetTs',
        COMMENT_IN_PROGRESS: 'commentInProgress',
        COMMENT_START_TIME: 'commentStartTime',
        ARM_SWITCH_DONE: 'armSwitchDone',
        ARM_SWITCH_IN_PROGRESS: 'armSwitchInProgress',
        MORNING_DONE: 'morningDone',
        MORNING_PRERELOAD: 'morningPrereload',
        PANEL_POS_X: 'panelPosX',
        PANEL_POS_Y: 'panelPosY',
        PANEL_COLLAPSED: 'panelCollapsed',
        MIGRATED_V3: '_migrated_v3'
    };

    // In-memory cache for synchronous reads in hot loops
    const cache = {};

    // Get today's date string
    function getTodayStr() {
        return new Date().toDateString();
    }

    // Sync getter - reads from memory cache instantly
    function getSync(key) {
        return cache[key] !== undefined ? cache[key] : null;
    }

    // Async setter - updates cache immediately, persists async
    async function setAsync(key, value) {
        cache[key] = value;
        try {
            await chrome.storage.local.set({ [key]: value });
        } catch (e) {
            console.error('[Storage] chrome.storage.local.set failed:', e);
        }
    }

    // Initialize: load all data from chrome.storage.local into memory cache
    async function init() {
        try {
            const all = await chrome.storage.local.get(null);
            Object.assign(cache, all);

            // Handle date rollover
            const today = getTodayStr();
            if (cache[KEYS.DATE] !== today) {
                cache[KEYS.COUNT] = '0';
                cache[KEYS.ANOMALY_COUNT] = '0';
                cache[KEYS.CONSECUTIVE_ANOMALIES] = '0';
                cache[KEYS.DATE] = today;
                // Clear daily task flags
                delete cache[KEYS.MORNING_DONE];
                delete cache[KEYS.MORNING_PRERELOAD];
                delete cache[KEYS.MORNING_TARGET];
                delete cache[KEYS.COMMENT_TASK_DONE];
                delete cache[KEYS.COMMENT_TASK_TARGET];
                delete cache[KEYS.COMMENT_IN_PROGRESS];
                delete cache[KEYS.COMMENT_START_TIME];
                delete cache[KEYS.ARM_SWITCH_DONE];
                delete cache[KEYS.ARM_SWITCH_IN_PROGRESS];
                await chrome.storage.local.set({
                    [KEYS.COUNT]: '0',
                    [KEYS.ANOMALY_COUNT]: '0',
                    [KEYS.CONSECUTIVE_ANOMALIES]: '0',
                    [KEYS.DATE]: today
                });
                // Remove daily keys
                await chrome.storage.local.remove([
                    KEYS.MORNING_DONE, KEYS.MORNING_PRERELOAD, KEYS.MORNING_TARGET,
                    KEYS.COMMENT_TASK_DONE, KEYS.COMMENT_TASK_TARGET,
                    KEYS.COMMENT_IN_PROGRESS, KEYS.COMMENT_START_TIME,
                    KEYS.ARM_SWITCH_DONE, KEYS.ARM_SWITCH_IN_PROGRESS
                ]);
            }

            console.log('[Storage] Initialized. Cache keys:', Object.keys(cache).filter(k => !k.startsWith('_')));
        } catch (e) {
            console.error('[Storage] Init failed:', e);
        }
    }

    // ============================================================
    // Storage API (mirrors original Storage object methods)
    // ============================================================
    const Storage = {
        // --- Count ---
        get() {
            const storedDate = getSync(KEYS.DATE);
            if (storedDate !== getTodayStr()) return 0;
            return parseInt(getSync(KEYS.COUNT) || '0', 10);
        },
        async add() {
            const current = this.get();
            await setAsync(KEYS.DATE, getTodayStr());
            await setAsync(KEYS.COUNT, String(current + 1));
        },
        async setCount(v) {
            await setAsync(KEYS.DATE, getTodayStr());
            await setAsync(KEYS.COUNT, String(v));
        },
        reset() {
            // Called from popup/message - handled in content-script.js
            if (confirm('确认重置所有数据？')) {
                // Clear cache
                Object.keys(cache).forEach(k => delete cache[k]);
                chrome.storage.local.clear();
                location.reload();
            }
        },

        // --- Morning ---
        getMorningTarget() {
            const storedDate = getSync(KEYS.DATE);
            const targetTs = getSync(KEYS.MORNING_TARGET);
            if (storedDate !== getTodayStr() || !targetTs) return null;
            return parseInt(targetTs, 10) || null;
        },
        async setMorningTarget(ts) {
            await setAsync(KEYS.DATE, getTodayStr());
            await setAsync(KEYS.MORNING_TARGET, String(ts));
        },

        // --- Anomaly ---
        getAnomalyCount() {
            const storedDate = getSync(KEYS.DATE);
            if (storedDate !== getTodayStr()) return 0;
            return parseInt(getSync(KEYS.ANOMALY_COUNT) || '0', 10);
        },
        async addAnomaly() {
            const current = this.getAnomalyCount();
            await setAsync(KEYS.DATE, getTodayStr());
            await setAsync(KEYS.ANOMALY_COUNT, String(current + 1));
        },
        async resetAnomaly() {
            await setAsync(KEYS.ANOMALY_COUNT, '0');
        },

        // --- Consecutive Anomalies ---
        getConsecutiveAnomalies() {
            return parseInt(getSync(KEYS.CONSECUTIVE_ANOMALIES) || '0', 10);
        },
        async setConsecutiveAnomalies(v) {
            await setAsync(KEYS.CONSECUTIVE_ANOMALIES, String(v));
        },

        // --- Anomaly Cooldown ---
        getAnomalyCooldown() {
            const v = getSync(KEYS.ANOMALY_COOLDOWN);
            return v ? parseInt(v, 10) : 0;
        },
        async setAnomalyCooldown(ts) {
            await setAsync(KEYS.ANOMALY_COOLDOWN, String(ts));
        },
        async clearAnomalyCooldown() {
            await setAsync(KEYS.ANOMALY_COOLDOWN, '0');
        },

        // --- Comment Task ---
        getCommentTarget() {
            const storedDate = getSync(KEYS.DATE);
            const targetTs = getSync(KEYS.COMMENT_TASK_TARGET);
            if (storedDate !== getTodayStr() || !targetTs) return null;
            return parseInt(targetTs, 10) || null;
        },
        async setCommentTarget(ts) {
            await setAsync(KEYS.DATE, getTodayStr());
            await setAsync(KEYS.COMMENT_TASK_TARGET, String(ts));
        },
        isCommentTaskDone() {
            return getSync(KEYS.COMMENT_TASK_DONE) === '1';
        },
        async markCommentTaskDone() {
            await setAsync(KEYS.COMMENT_TASK_DONE, '1');
        },
        isCommentInProgress() {
            return getSync(KEYS.COMMENT_IN_PROGRESS) === '1';
        },
        async setCommentInProgress(v) {
            await setAsync(KEYS.COMMENT_IN_PROGRESS, v ? '1' : '0');
            if (v) {
                await setAsync(KEYS.COMMENT_START_TIME, String(Date.now()));
            } else {
                await setAsync(KEYS.COMMENT_START_TIME, '0');
            }
        },
        getCommentTaskStartTime() {
            const v = getSync(KEYS.COMMENT_START_TIME);
            return v ? parseInt(v, 10) : 0;
        },
        isCommentTaskTimeout(timeoutMs) {
            if (!timeoutMs) timeoutMs = 5 * 60 * 1000; // default 5 min
            if (!this.isCommentInProgress()) return false;
            const startTime = this.getCommentTaskStartTime();
            if (!startTime) return false;
            return (Date.now() - startTime) > timeoutMs;
        },
        async resetCommentTaskState() {
            console.log('[Storage] 强制重置评论任务状态');
            await setAsync(KEYS.COMMENT_IN_PROGRESS, '0');
            await setAsync(KEYS.COMMENT_START_TIME, '0');
            await setAsync(KEYS.COMMENT_TASK_DONE, '0');
        },

        // --- Arm Switch ---
        isArmSwitchDone() {
            return getSync(KEYS.ARM_SWITCH_DONE) === '1';
        },
        async markArmSwitchDone() {
            await setAsync(KEYS.ARM_SWITCH_DONE, '1');
        },
        isArmSwitchInProgress() {
            return getSync(KEYS.ARM_SWITCH_IN_PROGRESS) === '1';
        },
        async setArmSwitchInProgress(v) {
            await setAsync(KEYS.ARM_SWITCH_IN_PROGRESS, v ? '1' : '0');
        },

        // --- Morning Done ---
        isMorningDone() {
            return getSync(KEYS.MORNING_DONE) === '1';
        },
        async markMorningDone() {
            await setAsync(KEYS.MORNING_DONE, '1');
        },
        isMorningPreReload() {
            return getSync(KEYS.MORNING_PRERELOAD) === '1';
        },
        async markMorningPreReload() {
            await setAsync(KEYS.MORNING_PRERELOAD, '1');
        },

        // --- Panel Position ---
        getPanelPosX() {
            return getSync(KEYS.PANEL_POS_X);
        },
        getPanelPosY() {
            return getSync(KEYS.PANEL_POS_Y);
        },
        async setPanelPos(x, y) {
            await setAsync(KEYS.PANEL_POS_X, String(x));
            await setAsync(KEYS.PANEL_POS_Y, String(y));
        },
        isPanelCollapsed() {
            return getSync(KEYS.PANEL_COLLAPSED) === '1';
        },
        async setPanelCollapsed(v) {
            await setAsync(KEYS.PANEL_COLLAPSED, v ? '1' : '0');
        },

        // --- Init flag ---
        isMigrated() {
            return getSync(KEYS.MIGRATED_V3) === '1';
        },
        async markMigrated() {
            await setAsync(KEYS.MIGRATED_V3, '1');
        }
    };

    PX.Storage = Storage;
    PX.StorageKeys = KEYS;
    PX.StorageInit = init;
})();
