// ============================================================
// PrismaX Extension - Arm Switch
// Auto-switch between Arena Arm and Training Gold Arm
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    function getElementByXPath(xpath) {
        try {
            return document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        } catch (e) {
            console.error('[ArmSwitch] XPath 解析失败:', xpath, e);
            return null;
        }
    }

    function isVisibleElement(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function clickXPath(xpath, label) {
        const el = getElementByXPath(xpath);
        if (!el || !isVisibleElement(el)) {
            console.log(`[ArmSwitch] 未找到或不可见: ${label}`);
            return false;
        }
        try {
            el.click();
            console.log(`[ArmSwitch] 已点击: ${label}`);
            return true;
        } catch (e) {
            console.error(`[ArmSwitch] 点击失败: ${label}`, e);
            return false;
        }
    }

    function findButtonNearElement(root, keywords) {
        if (!root) return null;
        const lowerKeywords = keywords.map(k => k.toLowerCase());
        const candidates = Array.from(root.querySelectorAll('button, div[role="button"], span'));
        return candidates.find(el => {
            if (!isVisibleElement(el)) return false;
            const text = (el.innerText || el.textContent || '').trim().toLowerCase();
            return lowerKeywords.some(k => text.includes(k));
        });
    }

    function clickElement(el, label) {
        if (!el || !isVisibleElement(el)) {
            console.log(`[ArmSwitch] 未找到或不可见: ${label}`);
            return false;
        }
        try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
        try {
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.click();
            console.log(`[ArmSwitch] 已点击: ${label}`);
            return true;
        } catch (e) {
            console.error(`[ArmSwitch] 点击失败: ${label}`, e);
            return false;
        }
    }

    function findArmElement(label, xpath) {
        const xpathEl = getElementByXPath(xpath);
        if (xpathEl && isVisibleElement(xpathEl)) return xpathEl;

        const candidates = Array.from(document.querySelectorAll('button, div[role="button"], div, li'));
        const pattern = new RegExp(`\\b${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
        const titleEl = candidates.find(el => {
            if (!isVisibleElement(el)) return false;
            const text = (el.innerText || el.textContent || '').trim();
            return pattern.test(text);
        });
        if (!titleEl) return null;

        return titleEl.closest('button, div[role="button"], li, [class*="Card"], [class*="card"]') || titleEl;
    }

    function joinArm(label, xpath, enterKeywords, config, attempt, done) {
        if (!attempt) attempt = 0;
        if (!done) done = function() {};

        const armEl = findArmElement(label, xpath);
        if (!armEl) {
            if (attempt < 20) {
                if (attempt === 0) console.log(`[ArmSwitch] 等待 ${label} 卡片加载...`);
                setTimeout(() => joinArm(label, xpath, enterKeywords, config, attempt + 1, done), 500);
            } else {
                console.log(`[ArmSwitch] 等待 ${label} 超时，未切换`);
                done(false);
            }
            return;
        }

        const clickedArm = clickElement(armEl, `${label} 卡片`);
        if (!clickedArm) {
            done(false);
            return;
        }

        setTimeout(() => {
            const cardRoot = armEl.closest('div') || armEl;
            const localEnter = findButtonNearElement(cardRoot, enterKeywords);
            if (localEnter) {
                done(clickElement(localEnter, `${label} 卡片内入队按钮`));
                return;
            }

            const globalEnter = PX.Automation ? PX.Automation.findBtn(enterKeywords) : null;
            if (globalEnter) {
                done(clickElement(globalEnter, '全局入队按钮'));
                return;
            }

            console.log(`[ArmSwitch] 未找到入队按钮，二次点击 ${label} 卡片尝试入队`);
            done(clickElement(armEl, `${label} 卡片（二次）`));
        }, 600);
    }

    function joinArenaArm(config, attempt, done) {
        joinArm('Arena Arm', config.armSwitchTask.arenaArmXPath, config.text.enter, config, attempt, done);
    }

    function joinTrainingGoldArm(config, attempt, done) {
        joinArm('Training Arm Gold', config.armSwitchTask.trainingGoldArmXPath, config.text.enter, config, attempt, done);
    }

    // Callback-based queue management helpers
    function hasLeaveQueueModal() {
        const confirmBtn = document.querySelector('button[class*="leaveModalConfirmBtn"], .QueuePanel_leaveModalConfirmBtn__ZtiIr');
        if (confirmBtn && isVisibleElement(confirmBtn)) return true;
        const exactBtn = Array.from(document.querySelectorAll('button, div[role="button"]')).find(el => {
            if (!isVisibleElement(el)) return false;
            const text = (el.innerText || el.textContent || '').trim().toLowerCase();
            return text === 'leave queue';
        });
        return !!exactBtn;
    }

    function confirmLeaveQueueIfPresent() {
        let confirmBtn = document.querySelector('button[class*="leaveModalConfirmBtn"], .QueuePanel_leaveModalConfirmBtn__ZtiIr');
        if (confirmBtn && !isVisibleElement(confirmBtn)) confirmBtn = null;
        if (!confirmBtn) {
            confirmBtn = Array.from(document.querySelectorAll('button, div[role="button"]')).find(el => {
                if (!isVisibleElement(el)) return false;
                const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                return text === 'leave queue';
            });
        }
        if (!confirmBtn) return false;
        try {
            confirmBtn.click();
            console.log('[ArmSwitch] 已确认离开队列弹窗');
            return true;
        } catch (e) {
            console.error('[ArmSwitch] 点击 Leave queue 确认失败:', e);
            return false;
        }
    }

    function waitUntilQueueLeft(done, config, attempt) {
        if (!attempt) attempt = 0;
        const modalStillOpen = hasLeaveQueueModal();
        const enterBtn = PX.Automation ? PX.Automation.findBtn(config.text.enter) : null;
        const queueBtn = PX.Automation ? PX.Automation.findBtn(config.text.queuing) : null;

        if (!modalStillOpen && (enterBtn || !queueBtn)) {
            console.log('[ArmSwitch] 已退出当前队列，可以切换手臂');
            done(true);
            return;
        }

        if (attempt >= 30) {
            console.log('[ArmSwitch] 等待退出队列超时');
            done(false);
            return;
        }

        setTimeout(() => waitUntilQueueLeft(done, config, attempt + 1), 500);
    }

    function confirmLeaveAndWait(done, config, attempt) {
        if (!attempt) attempt = 0;
        if (confirmLeaveQueueIfPresent()) {
            setTimeout(() => waitUntilQueueLeft(done, config), 500);
            return;
        }
        if (attempt >= 12) {
            console.log('[ArmSwitch] 未检测到离队确认弹窗，继续等待退出状态');
            waitUntilQueueLeft(done, config);
            return;
        }
        setTimeout(() => confirmLeaveAndWait(done, config, attempt + 1), 250);
    }

    function clickEnterAfterLeave(config) {
        const enter = PX.Automation ? PX.Automation.findBtn(config.text.enter) : null;
        if (enter) {
            try {
                enter.click();
                console.log('[ArmSwitch] 已重新进入队列');
            } catch (e) {
                console.error('[ArmSwitch] 重新进入队列失败:', e);
            }
        } else {
            console.log('[ArmSwitch] 未找到重新进入按钮，等待主循环继续扫描');
        }
    }

    function waitConfirmThenEnter(config, attempt) {
        if (!attempt) attempt = 0;
        if (confirmLeaveQueueIfPresent()) {
            setTimeout(() => waitUntilQueueLeft(() => clickEnterAfterLeave(config), config), 500);
            return;
        }
        if (attempt >= 10) {
            console.log('[ArmSwitch] 未检测到离队确认弹窗，尝试直接重新进入');
            waitUntilQueueLeft(() => clickEnterAfterLeave(config), config);
            return;
        }
        setTimeout(() => waitConfirmThenEnter(config, attempt + 1), 250);
    }

    function leaveQueueThenReenter(queueBtn, config) {
        try { queueBtn.click(); } catch (e) {
            console.error('[ArmSwitch] 点击离队按钮失败:', e);
        }
        setTimeout(() => waitConfirmThenEnter(config, 0), 250);
    }

    function waitLeaveConfirmThenSwitchArena(config, storage, attempt) {
        if (!attempt) attempt = 0;
        const cfg = config.armSwitchTask;

        if (confirmLeaveQueueIfPresent() || attempt >= 10) {
            waitUntilQueueLeft((leftOk) => {
                if (!leftOk) {
                    storage.setArmSwitchInProgress(false);
                    PX._autoState.armSwitchInProgress = false;
                    PX.Panel.updateUI('未能退出 Gold 队列，Arena 切换中止', '--', '--', '#ff3333', storage);
                    return;
                }
                const avatarClicked = clickXPath(cfg.robotAvatarXPath, '左侧机器人头像');
                setTimeout(() => {
                    joinArenaArm(config, 0, (arenaClicked) => {
                        if (arenaClicked) {
                            storage.markArmSwitchDone();
                            PX.Panel.updateUI('已切换到 Arena Arm', '--', '--', '#00ff99', storage);
                        } else {
                            storage.setArmSwitchInProgress(false);
                            PX.Panel.updateUI('Arena Arm 切换失败，等待重试', '--', '--', '#ff3333', storage);
                        }
                        PX._autoState.armSwitchInProgress = false;
                        console.log(`[ArmSwitch] Arena Arm 切换完成 avatar=${avatarClicked} arena=${arenaClicked}`);
                    });
                }, cfg.afterAvatarDelay);
            }, config);
            return;
        }
        setTimeout(() => waitLeaveConfirmThenSwitchArena(config, storage, attempt + 1), 250);
    }

    function switchToArenaArm(queueBtn, config, storage) {
        if (PX._autoState.armSwitchInProgress || storage.isArmSwitchInProgress()) return;
        PX._autoState.armSwitchInProgress = true;
        storage.setArmSwitchInProgress(true);
        PX.Panel.updateUI('训练金臂已完成 6 次，切换 Arena Arm...', '--', '--', '#66ccff', storage);
        console.log('[ArmSwitch] 开始切换到 Arena Arm');

        if (queueBtn) {
            try { queueBtn.click(); } catch (e) {
                console.error('[ArmSwitch] 点击离队按钮失败:', e);
            }
            setTimeout(() => waitLeaveConfirmThenSwitchArena(config, storage, 0), 250);
        } else {
            waitLeaveConfirmThenSwitchArena(config, storage, 10);
        }
    }

    function maybeSwitchToArenaArm(queueBtn, config, storage) {
        const cfg = config.armSwitchTask;
        if (!cfg.enabled) return false;
        if (storage.isArmSwitchDone() || storage.isArmSwitchInProgress() || PX._autoState.armSwitchInProgress) return false;
        if (storage.get() < cfg.successThreshold) return false;
        switchToArenaArm(queueBtn, config, storage);
        return true;
    }

    function returnToTrainingGold(queueBtn, config, storage, notifier) {
        const cfg = config.armSwitchTask;
        PX.Panel.updateUI('早八: 正在切回 Training Arm Gold...', '--', '--', '#66ccff', storage);

        const switchGold = () => {
            const avatarClicked = clickXPath(cfg.robotAvatarXPath, '左侧机器人头像');
            setTimeout(() => {
                joinTrainingGoldArm(config, 0, (goldClicked) => {
                    if (goldClicked) {
                        storage.setCount(0);
                        storage.resetAnomaly();
                        storage.setArmSwitchInProgress(false);
                        PX._autoState.armSwitchInProgress = false;
                        PX._autoState.morningRequeueActive = true;
                        const c = document.getElementById('p-count');
                        if (c) c.innerText = "0";
                        PX.Panel.updateAnomalyUI(storage);
                        PX.Panel.updateUI('早八: 已切回 Training Arm Gold', '--', '--', '#00ff99', storage);
                    } else {
                        storage.setArmSwitchInProgress(false);
                        PX._autoState.armSwitchInProgress = false;
                        PX.Panel.updateUI('早八: 切回 Gold 失败，等待重试', '--', '--', '#ff3333', storage);
                    }
                    console.log(`[ArmSwitch] Gold 切换完成 avatar=${avatarClicked} gold=${goldClicked}`);
                });
            }, cfg.afterAvatarDelay);
        };

        if (queueBtn) {
            PX._autoState.armSwitchInProgress = true;
            storage.setArmSwitchInProgress(true);
            try { queueBtn.click(); } catch (e) {
                console.error('[ArmSwitch] 点击离队按钮失败:', e);
            }
            setTimeout(() => confirmLeaveAndWait((leftOk) => {
                if (!leftOk) {
                    storage.setArmSwitchInProgress(false);
                    PX._autoState.armSwitchInProgress = false;
                    PX.Panel.updateUI('早八: 未能退出当前队列', '--', '--', '#ff3333', storage);
                    return;
                }
                switchGold();
            }, config), 250);
        } else {
            switchGold();
        }
    }

    function debugArenaArmSwitch(config, storage) {
        const arena = findArmElement('Arena Arm', config.armSwitchTask.arenaArmXPath);
        const gold = findArmElement('Training Arm Gold', config.armSwitchTask.trainingGoldArmXPath);
        const avatar = getElementByXPath(config.armSwitchTask.robotAvatarXPath);
        const queueBtn = PX.Automation ? PX.Automation.findBtn(config.text.queuing) : null;
        const result = {
            avatarFound: !!avatar,
            avatarVisible: !!avatar && isVisibleElement(avatar),
            arenaFound: !!arena,
            arenaVisible: !!arena && isVisibleElement(arena),
            goldFound: !!gold,
            goldVisible: !!gold && isVisibleElement(gold),
            queueButtonFound: !!queueBtn,
            armSwitchDone: storage.isArmSwitchDone(),
            armSwitchInProgress: storage.isArmSwitchInProgress() || PX._autoState.armSwitchInProgress
        };
        console.table(result);
        return result;
    }

    PX.ArmSwitch = {
        getElementByXPath: getElementByXPath,
        isVisibleElement: isVisibleElement,
        clickXPath: clickXPath,
        clickElement: clickElement,
        findArmElement: findArmElement,
        joinArenaArm: joinArenaArm,
        joinTrainingGoldArm: joinTrainingGoldArm,
        confirmLeaveQueueIfPresent: confirmLeaveQueueIfPresent,
        hasLeaveQueueModal: hasLeaveQueueModal,
        waitUntilQueueLeft: waitUntilQueueLeft,
        confirmLeaveAndWait: confirmLeaveAndWait,
        clickEnterAfterLeave: clickEnterAfterLeave,
        leaveQueueThenReenter: leaveQueueThenReenter,
        switchToArenaArm: switchToArenaArm,
        maybeSwitchToArenaArm: maybeSwitchToArenaArm,
        returnToTrainingGold: returnToTrainingGold,
        debugArenaArmSwitch: debugArenaArmSwitch
    };
})();
