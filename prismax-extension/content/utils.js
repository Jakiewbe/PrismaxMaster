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

    function isVisibleElement(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function getElementText(el) {
        if (!el) return '';
        return [
            el.innerText,
            el.textContent,
            el.getAttribute && el.getAttribute('aria-label'),
            el.getAttribute && el.getAttribute('title'),
            el.getAttribute && el.getAttribute('value')
        ].filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
    }

    function toActionElement(el) {
        if (!el) return null;
        return el.closest && el.closest('button, [role="button"], input[type="button"], input[type="submit"]') || el;
    }

    function findClickableByKeywords(keywords, options) {
        const opts = options || {};
        const blacklist = opts.blacklist || [];
        const excludeLeave = !!opts.excludeLeave;
        const candidates = Array.from(document.querySelectorAll(
            'button, [role="button"], input[type="button"], input[type="submit"], span'
        ));

        for (const el of candidates) {
            const actionEl = toActionElement(el);
            if (!isVisibleElement(actionEl)) continue;
            if (actionEl.tagName === 'A' || actionEl.closest('a')) continue;

            const text = getElementText(actionEl);
            if (!text) continue;
            if (blacklist.some(bad => text.includes(bad))) continue;

            const lower = text.toLowerCase();
            if (excludeLeave && lower.includes('leave')) continue;
            if (keywords.some(k => lower.includes(String(k).toLowerCase()))) return actionEl;
        }
        return null;
    }

    function parseQueueRank(text) {
        if (!text) return null;
        const frontMatch = text.match(/(\d{1,4})\s*(?:users?|people)\s+in\s+front/i) ||
            text.match(/There'?s\s+(\d{1,4})\s+users?\s+in\s+front\s+of\s+you/i);
        if (frontMatch) return parseInt(frontMatch[1], 10) + 1;

        const patterns = [
            /Position[:\s#]+(\d{1,4})/i,
            /Queue[:\s#]+(\d{1,4})/i,
            /Waiting[:\s#]+(\d{1,4})/i,
            /(?:Rank|Queue\s*Position)\D{0,10}#?\s*(\d{1,4})/i,
            /#\s*(\d{1,4})\s*(?:in\s+queue|queued)/i,
            /(\d{1,4})\s*in\s*queue/i
        ];
        for (const pattern of patterns) {
            const match = text.match(pattern);
            if (match) return parseInt(match[1], 10);
        }
        return null;
    }

    PX.Utils = {
        getTodayStr: getTodayStr,
        getRandomInt: getRandomInt,
        formatDurationMs: formatDurationMs,
        parseTimeToday: parseTimeToday,
        recordScriptError: recordScriptError,
        isVisibleElement: isVisibleElement,
        getElementText: getElementText,
        toActionElement: toActionElement,
        findClickableByKeywords: findClickableByKeywords,
        parseQueueRank: parseQueueRank
    };
})();
