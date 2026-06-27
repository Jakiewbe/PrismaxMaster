// ============================================================
// PrismaX Extension - Arm Switch v2
// Text+class based arm selection (no hardcoded XPaths)
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    function isVisibleElement(el) {
        return PX.Utils && PX.Utils.isVisibleElement ? PX.Utils.isVisibleElement(el) : !!el;
    }

    function getElementText(el) {
        return PX.Utils && PX.Utils.getElementText
            ? PX.Utils.getElementText(el)
            : ((el && (el.innerText || el.textContent)) || '').trim();
    }

    function clickElement(el, label) {
        if (!el || !isVisibleElement(el)) {
            console.log('[ArmSwitch] not found/hidden:', label);
            return false;
        }
        try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
        try {
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.click();
            console.log('[ArmSwitch] clicked:', label);
            return true;
        } catch (e) {
            console.error('[ArmSwitch] click failed:', label, e);
            return false;
        }
    }

    // v2: find arm card by label text, then find its join/enqueue button
    function findArmCard(label) {
        const candidates = Array.from(document.querySelectorAll('[class*="robotName"], [class*="robotCard"], h3, div'));
        for (const el of candidates) {
            const text = getElementText(el);
            if (text === label || text.includes(label)) {
                // Walk up to find the card container
                return el.closest('[class*="robotCard"], [class*="card"], [class*="Card"]') || el.closest('div');
            }
        }
        // Fallback: search all text
        for (const el of Array.from(document.querySelectorAll('h3, [class*="name"], [class*="Name"]'))) {
            if (getElementText(el).trim() === label) {
                return el.closest('div');
            }
        }
        return null;
    }

    // v2: find join/enqueue button inside a card container
    function findJoinButtonInCard(cardEl) {
        if (!cardEl) return null;
        const btns = Array.from(cardEl.querySelectorAll('button, [role="button"]'));
        for (const btn of btns) {
            if (!isVisibleElement(btn)) continue;
            const text = getElementText(btn).toLowerCase();
            if (/join|enter|start|begin|queue|control|入队|进入/.test(text)) return btn;
        }
        return null;
    }

    function isActiveArm(label) {
        const card = findArmCard(label);
        if (!card) return false;
        const stateText = (card.className || '') + ' ' +
            (card.getAttribute('aria-selected') || '') + ' ' +
            (card.getAttribute('data-active') || '');
        return /(active|selected|current|true)/i.test(stateText);
    }

    function isQueuedOnArm(label, config) {
        const queueBtn = PX.Automation ? PX.Automation.findBtn(config.text.queuing) : null;
        if (queueBtn) {
            const currentArm = PX.Storage && PX.Storage.getCurrentArm ? PX.Storage.getCurrentArm() : '';
            if (currentArm && currentArm === label) return true;
        }
        return false;
    }

    function getGoldAttemptCount(storage) {
        return storage.get() + storage.getAnomalyCount();
    }

    // v2: join an arm by clicking its card, then clicking the join button inside it
    function joinArm(label, config, attempt, done) {
        if (!attempt) attempt = 0;
        if (!done) done = function() {};

        if (isQueuedOnArm(label, config)) {
            console.log('[ArmSwitch] already queued on ' + label);
            done(true);
            return;
        }

        const card = findArmCard(label);
        if (!card) {
            if (attempt < 20) {
                if (attempt === 0) console.log('[ArmSwitch] waiting for ' + label + ' card...');
                setTimeout(() => joinArm(label, config, attempt + 1, done), 500);
            } else {
                console.log('[ArmSwitch] timeout waiting for ' + label);
                done(false);
            }
            return;
        }

        if (!clickElement(card, label + ' card')) { done(false); return; }

        setTimeout(() => {
            const joinBtn = findJoinButtonInCard(card) ||
                (PX.Automation ? PX.Automation.findBtn(config.text.enter) : null);
            if (joinBtn) {
                done(clickElement(joinBtn, 'join button for ' + label));
            } else {
                console.log('[ArmSwitch] no join button found for ' + label);
                done(false);
            }
        }, 600);
    }

    function joinArenaArm(config, attempt, done) {
        joinArm((config.armSwitchTask || {}).arenaArmLabel || 'Arena Arm', config, attempt, done);
    }

    function joinTrainingGoldArm(config, attempt, done) {
        joinArm((config.armSwitchTask || {}).trainingGoldLabel || 'Training Arm Gold', config, attempt, done);
    }

    // v2: queue management helpers (no XPaths)
    function hasLeaveQueueModal() {
        const modalBtn = document.querySelector('button[class*="leaveModal"], .QueuePanel_leaveModalConfirmBtn__ZtiIr');
        if (modalBtn && isVisibleElement(modalBtn)) return true;
        return !!Array.from(document.querySelectorAll('button, [role="button"]')).find(el => {
            return isVisibleElement(el) && getElementText(el).toLowerCase() === 'leave queue';
        });
    }

    function confirmLeaveQueueIfPresent() {
        const btn = document.querySelector('button[class*="leaveModal"]') ||
            Array.from(document.querySelectorAll('button, [role="button"]')).find(el =>
                isVisibleElement(el) && getElementText(el).toLowerCase() === 'leave queue');
        if (!btn) return false;
        try { btn.click(); console.log('[ArmSwitch] confirmed leave queue'); return true; }
        catch (e) { console.error('[ArmSwitch] leave confirm failed:', e); return false; }
    }

    function waitUntilQueueLeft(done, config, attempt) {
        if (!attempt) attempt = 0;
        const modalOpen = hasLeaveQueueModal();
        const enterBtn = PX.Automation ? PX.Automation.findBtn(config.text.enter) : null;
        const queueBtn = PX.Automation ? PX.Automation.findBtn(config.text.queuing) : null;
        if (!modalOpen && (enterBtn || !queueBtn)) { done(true); return; }
        if (attempt >= 30) { console.log('[ArmSwitch] wait-queue-left timeout'); done(false); return; }
        setTimeout(() => waitUntilQueueLeft(done, config, attempt + 1), 500);
    }

    function confirmLeaveAndWait(done, config, attempt) {
        if (!attempt) attempt = 0;
        if (confirmLeaveQueueIfPresent()) { setTimeout(() => waitUntilQueueLeft(done, config), 500); return; }
        if (attempt >= 12) { waitUntilQueueLeft(done, config); return; }
        setTimeout(() => confirmLeaveAndWait(done, config, attempt + 1), 250);
    }

    function leaveQueueThenReenter(queueBtn, config) {
        try { queueBtn.click(); } catch (e) { console.error('[ArmSwitch] leave click failed:', e); }
        setTimeout(() => {
            const doEnter = () => {
                const enter = PX.Automation ? PX.Automation.findBtn(config.text.enter) : null;
                if (enter) { try { enter.click(); console.log('[ArmSwitch] re-entered queue'); } catch (e2) {} }
                else { console.log('[ArmSwitch] no enter button, waiting for main loop'); }
            };
            confirmLeaveAndWait((ok) => { if (ok) doEnter(); }, config);
        }, 250);
    }

    function switchToArenaArm(queueBtn, config, storage) {
        if (PX._autoState.armSwitchInProgress || storage.isArmSwitchInProgress()) return;
        const arenaLabel = (config.armSwitchTask || {}).arenaArmLabel || 'Arena Arm';
        if (isQueuedOnArm(arenaLabel, config)) {
            storage.markArmSwitchDone();
            storage.setArmSwitchInProgress(false);
            PX._autoState.armSwitchInProgress = false;
            PX.Panel.updateUI('already on Arena queue', '--', '--', '#00ff99', storage);
            return;
        }
        PX._autoState.armSwitchInProgress = true;
        storage.setArmSwitchInProgress(true);
        const attempts = getGoldAttemptCount(storage);
        PX.Panel.updateUI('Gold ' + attempts + ' attempts, switching to Arena...', '--', '--', '#66ccff', storage);

        const doSwitch = () => {
            joinArenaArm(config, 0, (ok) => {
                if (ok) {
                    storage.markArmSwitchDone();
                    if (storage.setCurrentArm) storage.setCurrentArm(arenaLabel);
                    PX.Panel.updateUI('Switched to Arena Arm', '--', '--', '#00ff99', storage);
                } else {
                    storage.setArmSwitchInProgress(false);
                    PX.Panel.updateUI('Arena switch failed, retrying', '--', '--', '#ff3333', storage);
                }
                PX._autoState.armSwitchInProgress = false;
            });
        };

        if (queueBtn) {
            try { queueBtn.click(); } catch (e) {}
            setTimeout(() => confirmLeaveAndWait((ok) => { if (ok) doSwitch(); else {
                storage.setArmSwitchInProgress(false);
                PX._autoState.armSwitchInProgress = false;
            }}, config), 250);
        } else { doSwitch(); }
    }

    function maybeSwitchToArenaArm(queueBtn, config, storage) {
        const cfg = config.armSwitchTask;
        if (!cfg.enabled) return false;
        if (storage.isArmSwitchDone() || storage.isArmSwitchInProgress() || PX._autoState.armSwitchInProgress) return false;
        if (getGoldAttemptCount(storage) < cfg.successThreshold) return false;
        switchToArenaArm(queueBtn, config, storage);
        return true;
    }

    function returnToTrainingGold(queueBtn, config, storage, notifier) {
        const cfg = config.armSwitchTask;
        const goldLabel = cfg.trainingGoldLabel || 'Training Arm Gold';
        if (isQueuedOnArm(goldLabel, config)) {
            storage.setCount(0); storage.resetAnomaly();
            if (storage.clearArmSwitchDone) storage.clearArmSwitchDone();
            if (storage.setCurrentArm) storage.setCurrentArm(goldLabel);
            storage.setArmSwitchInProgress(false);
            PX._autoState.armSwitchInProgress = false;
            PX._autoState.morningRequeueActive = true;
            PX.Panel.updateUI('already on Gold queue', '--', '--', '#00ff99', storage);
            return;
        }
        PX.Panel.updateUI('morning: switching to Gold...', '--', '--', '#66ccff', storage);

        const doSwitchGold = () => {
            joinTrainingGoldArm(config, 0, (ok) => {
                if (ok) {
                    storage.setCount(0); storage.resetAnomaly();
                    if (storage.clearArmSwitchDone) storage.clearArmSwitchDone();
                    if (storage.setCurrentArm) storage.setCurrentArm(goldLabel);
                    PX._autoState.morningRequeueActive = true;
                    PX.Panel.updateUI('morning: switched to Gold', '--', '--', '#00ff99', storage);
                } else {
                    PX.Panel.updateUI('morning: Gold switch failed', '--', '--', '#ff3333', storage);
                }
                storage.setArmSwitchInProgress(false);
                PX._autoState.armSwitchInProgress = false;
            });
        };

        if (queueBtn) {
            PX._autoState.armSwitchInProgress = true;
            storage.setArmSwitchInProgress(true);
            try { queueBtn.click(); } catch (e) {}
            setTimeout(() => confirmLeaveAndWait((ok) => {
                if (ok) doSwitchGold();
                else { storage.setArmSwitchInProgress(false); PX._autoState.armSwitchInProgress = false; }
            }, config), 250);
        } else { doSwitchGold(); }
    }

    function debugArenaArmSwitch(config, storage) {
        const cfg = config.armSwitchTask;
        const arena = findArmCard(cfg.arenaArmLabel || 'Arena Arm');
        const gold = findArmCard(cfg.trainingGoldLabel || 'Training Arm Gold');
        const queueBtn = PX.Automation ? PX.Automation.findBtn(config.text.queuing) : null;
        const result = {
            arenaFound: !!arena, goldFound: !!gold,
            arenaVisible: !!(arena && isVisibleElement(arena)),
            goldVisible: !!(gold && isVisibleElement(gold)),
            queueButtonFound: !!queueBtn,
            queuedArena: isQueuedOnArm(cfg.arenaArmLabel || 'Arena Arm', config),
            queuedGold: isQueuedOnArm(cfg.trainingGoldLabel || 'Training Arm Gold', config),
            goldAttempts: getGoldAttemptCount(storage),
            armSwitchDone: storage.isArmSwitchDone(),
            armSwitchInProgress: storage.isArmSwitchInProgress() || PX._autoState.armSwitchInProgress
        };
        console.table(result);
        return result;
    }

    PX.ArmSwitch = {
        isVisibleElement, clickElement, findArmCard, findJoinButtonInCard,
        joinArenaArm, joinTrainingGoldArm,
        confirmLeaveQueueIfPresent, hasLeaveQueueModal,
        waitUntilQueueLeft, confirmLeaveAndWait,
        leaveQueueThenReenter, switchToArenaArm, maybeSwitchToArenaArm,
        returnToTrainingGold, isActiveArm, isQueuedOnArm,
        getGoldAttemptCount, debugArenaArmSwitch
    };
})();
