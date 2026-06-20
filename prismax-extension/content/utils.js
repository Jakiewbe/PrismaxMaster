// ============================================================
// PrismaX Extension - Utility Functions
// Shared helpers used across all modules
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    function getTodayStr() {
        return new Date().toDateString();
    }

    function getRandomInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    function formatDurationMs(ms) {
        if (ms < 0) ms = 0;
        const m = Math.floor(ms / 60000);
        const s = Math.floor((ms % 60000) / 1000);
        return `${m}m ${s}s`;
    }

    function parseTimeToday(hm) {
        if (!hm || typeof hm !== 'string') return null;
        const parts = hm.split(':');
        if (parts.length !== 2) return null;
        const h = parseInt(parts[0], 10);
        const m = parseInt(parts[1], 10);
        if (isNaN(h) || isNaN(m)) return null;
        const d = new Date();
        d.setHours(h, m, 0, 0);
        return d;
    }

    function recordScriptError(scope, error) {
        const message = `[${scope}] ${error && error.message ? error.message : String(error)}`;
        PX._lastError = message;
        console.error('[PRISMAX脚本错误]', message, error);
    }

    PX.Utils = {
        getTodayStr: getTodayStr,
        getRandomInt: getRandomInt,
        formatDurationMs: formatDurationMs,
        parseTimeToday: parseTimeToday,
        recordScriptError: recordScriptError
    };
})();
