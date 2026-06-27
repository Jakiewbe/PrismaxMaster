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


    function isDataReviewPage() {
        return location.hostname === 'app.prismax.ai' && location.pathname.indexOf('/data/review') === 0;
    }

    function isDataReviewListPage() {
        return location.hostname === 'app.prismax.ai' && location.pathname.replace(/\/$/, '') === '/data/review';
    }


    const PAGE_MODES = {
        CONTROL: 'CONTROL_MODE',
        VLA_REVIEW: 'VLA_REVIEW_MODE',
        IDLE: 'IDLE_MODE'
    };

    function detectPageMode() {
        if (isDataReviewPage()) return PAGE_MODES.VLA_REVIEW;
        if (location.hostname !== 'app.prismax.ai') return PAGE_MODES.IDLE;
        const path = location.pathname || '';
        if (path.includes('/live-control') || path.includes('/robots-center')) return PAGE_MODES.CONTROL;
        const bodyText = document.body ? (document.body.innerText || '') : '';
        if (/End\s+(Tele-Operation|Session|Control)|Leave\s+Queue|Join\s+Queue|Enter\s+Live\s+Control/i.test(bodyText)) {
            return PAGE_MODES.CONTROL;
        }
        if (findValidationEntryButton()) return PAGE_MODES.CONTROL;
        return PAGE_MODES.IDLE;
    }

    const actionLockState = { owner: null, until: 0, reason: '' };

    const ActionLock = {
        acquire(owner, ttlMs, reason) {
            const now = Date.now();
            if (actionLockState.owner && actionLockState.until > now && actionLockState.owner !== owner) {
                return false;
            }
            actionLockState.owner = owner;
            actionLockState.until = now + Math.max(1000, ttlMs || 10000);
            actionLockState.reason = reason || '';
            return true;
        },
        release(owner) {
            if (!owner || actionLockState.owner === owner || actionLockState.until <= Date.now()) {
                actionLockState.owner = null;
                actionLockState.until = 0;
                actionLockState.reason = '';
                return true;
            }
            return false;
        },
        isLocked() {
            if (actionLockState.owner && actionLockState.until <= Date.now()) this.release(actionLockState.owner);
            return !!actionLockState.owner;
        },
        getOwner() {
            return this.isLocked() ? actionLockState.owner : null;
        },
        getState() {
            return {
                owner: this.getOwner(),
                until: actionLockState.until,
                reason: actionLockState.reason
            };
        }
    };

    function findReviewEarnButton() {
        const candidates = Array.from(document.querySelectorAll('button, [role="button"]'));
        for (const el of candidates) {
            const actionEl = toActionElement(el);
            if (!isVisibleElement(actionEl)) continue;
            if (actionEl.disabled || actionEl.getAttribute('aria-disabled') === 'true') continue;
            const text = getElementText(actionEl);
            if (/Review\s*&\s*Earn/i.test(text)) return actionEl;
        }
        return null;
    }

    function findValidationEntryButton() {
        return findClickableByKeywords(['Begin Validating', 'Start Validating', 'Control Now'], {
            blacklist: ['Connect Wallet', 'MetaMask', 'Phantom', 'OKX'],
            excludeLeave: true
        });
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

    PX.ActionLock = ActionLock;

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
        isDataReviewPage: isDataReviewPage,
        isDataReviewListPage: isDataReviewListPage,
        findReviewEarnButton: findReviewEarnButton,
        findValidationEntryButton: findValidationEntryButton,
        PAGE_MODES: PAGE_MODES,
        detectPageMode: detectPageMode,
        ActionLock: ActionLock,
        parseQueueRank: parseQueueRank
    };
})();
