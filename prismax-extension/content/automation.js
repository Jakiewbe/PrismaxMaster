// ============================================================
// PrismaX Extension - Main Automation Loop
// Queue monitoring, auto-click, session tracking, anomaly detection
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    // ============================================================
    // DOM Utility Functions
    // ============================================================

    function getElementText(el) {
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

    function findBtn(keywords, blacklist) {
        const bl = blacklist || (PX._config && PX._config.text ? PX._config.text.blacklist : []);
        const enterKeys = PX._config && PX._config.text ? PX._config.text.enter : [];
        const candidates = Array.from(document.querySelectorAll(
            'button, [role="button"], input[type="button"], input[type="submit"], span'
        ));
        for (const el of candidates) {
            const actionEl = toActionElement(el);
            if (!isVisibleElement(actionEl)) continue;
            if (actionEl.tagName === 'A' || actionEl.closest('a')) continue;
            const txt = getElementText(actionEl);
            if (!txt) continue;
            if (bl.some(bad => txt.includes(bad))) continue;
            const lower = txt.toLowerCase();
            const isMatch = keywords.some(k => lower.includes(k.toLowerCase()));
            if (isMatch && keywords === enterKeys && lower.includes("leave")) continue;
            if (isMatch) return actionEl;
        }
        return null;
    }

    function isVisibleElement(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function getRankContextText() {
        const els = Array.from(document.querySelectorAll('div, span, p, li, h1, h2, h3, h4, h5, h6'));
        const queueEl = els.find(el => (el.innerText || '').includes('You are now in the queue.'));
        if (queueEl) return queueEl.innerText || '';
        return document.body ? (document.body.innerText || '') : '';
    }

    function parseRawRank(text) {
        if (!text) return null;
        // Pattern 1: "X users in front"
        const m1 = text.match(/(\d{1,4})\s*(?:users?|people)\s+in\s+front/i);
        if (m1) return parseInt(m1[1], 10);
        // Pattern 2: "Position: X"
        const m2 = text.match(/Position[:\s]+(\d{1,4})/i);
        if (m2) return parseInt(m2[1], 10) - 1;
        // Pattern 3: "Queue: X"
        const m3 = text.match(/Queue[:\s]+(\d{1,4})/i);
        if (m3) return parseInt(m3[1], 10) - 1;
        // Pattern 4: "Waiting: X"
        const m4 = text.match(/Waiting[:\s]+(\d{1,4})/i);
        if (m4) return parseInt(m4[1], 10) - 1;
        // Pattern 5: "Rank #X" / "#X in queue"
        const m5 = text.match(/(?:Rank|Queue\s*Position)\D{0,10}#?\s*(\d{1,4})/i) ||
            text.match(/#\s*(\d{1,4})\s*(?:in\s+queue|queued)/i);
        if (m5) return parseInt(m5[1], 10) - 1;
        return null;
    }

    function getActiveTimerString(text) {
        if (!text) return null;
        const m = text.match(/Active[:\s]+(\d{1,3}:\d{2})/i);
        return m ? m[1] : null;
    }

    function randomStuckLimitMs(config) {
        if (!config) return 330000;
        return PX.Utils.getRandomInt(config.stuckToleranceMin * 1000, config.stuckToleranceMax * 1000);
    }

    // ============================================================
    // Main Automation Loop
    // ============================================================

    function loopUnsafe(config, storage, notifier, controller) {
        if (!document.body) { setTimeout(() => loopWrapper(config, storage, notifier, controller), 1000); return; }
        PX._loopHeartbeatAt = Date.now();
        PX.Panel.createPanel(storage, PX._scriptPausedRef);

        const now = Date.now();
        PX.Morning.updateWatchdogHeartbeat();

        // Day change detection
        const currentDay = PX.Utils.getTodayStr();
        if (currentDay !== (PX._startDay || currentDay)) {
            PX.Morning.safeReload("跨天自动刷新", notifier);
            return;
        }

        // Morning window check
        const win = PX.Morning.getMorningWindowMs(config);
        if (win) {
            const { startMs, endMs } = win;
            const inWindow = now >= startMs && now <= endMs;
            PX.Morning.setInMorningWindow(inWindow);
            if (inWindow) {
                PX.Morning.startMorningWatchdog(config, storage);
            } else {
                PX.Morning.stopMorningWatchdog();
                PX.Morning.setInMorningWindow(false);
            }
        }

        // Morning pre-reload
        if (win && !storage.isMorningDone() && !storage.isMorningPreReload()) {
            const { startMs } = win;
            if (now >= startMs - 60000 && now < startMs) {
                console.log("[Stark HUD] 触发早八前预刷新");
                storage.markMorningPreReload();
                PX.Morning.safeReload("早八前预刷新", notifier);
                return;
            }
        }

        // Morning trigger check
        if (win && !storage.isMorningDone() && !PX._autoState.morningTriggeredAt) {
            const { startMs, endMs } = win;
            if (config.morningRandomInsideWindow) {
                let targetMs = storage.getMorningTarget();
                if (!targetMs || targetMs < startMs || targetMs > endMs) {
                    targetMs = PX.Utils.getRandomInt(startMs, endMs - 1);
                    storage.setMorningTarget(targetMs);
                    console.log("[Stark HUD] 生成并保存早八时间:", new Date(targetMs).toLocaleTimeString());
                }
                if (now >= targetMs && now <= endMs) {
                    PX.Morning.performMorningRequeue(config, storage, notifier);
                }
            } else {
                if (now >= startMs && now <= endMs) {
                    PX.Morning.performMorningRequeue(config, storage, notifier);
                }
            }
        }

        PX.Morning.updateMorningInfo(config, storage);

        // Comment task timeout detection
        if (storage.isCommentInProgress() && storage.isCommentTaskTimeout()) {
            console.log('[评论任务] ⚠️ 主循环检测到任务超时，执行自动重置');
            storage.resetCommentTaskState();
            PX.Panel.updateCommentTaskUI(storage);
        }

        // Comment task trigger
        const commentWin = PX.CommentTask.getCommentWindowMs(config);
        if (commentWin && !storage.isCommentTaskDone() && !storage.isCommentInProgress()) {
            const { startMs, endMs } = commentWin;
            if (config.commentTask.randomInsideWindow) {
                let targetMs = storage.getCommentTarget();
                if (!targetMs || targetMs < startMs || targetMs > endMs) {
                    targetMs = PX.Utils.getRandomInt(startMs, endMs - 1);
                    storage.setCommentTarget(targetMs);
                    console.log("[评论任务] 生成并保存触发时间:", new Date(targetMs).toLocaleTimeString());
                }
                if (now >= targetMs && now <= endMs) {
                    PX.CommentTask.performCommentTask(config, storage, notifier);
                }
            } else {
                if (now >= startMs && now <= endMs) {
                    PX.CommentTask.performCommentTask(config, storage, notifier);
                }
            }
        }
        PX.Panel.updateCommentTaskUI(storage);

        // Pause check
        if (PX._scriptPaused) {
            PX.Panel.updateUI("脚本已暂停（点击底部按钮恢复）", "--", "--", "gray", storage);
            setTimeout(() => loopWrapper(config, storage, notifier, controller), 1000);
            return;
        }

        // Button detection
        const enterBtn = findBtn(config.text.enter);
        const endBtn = findBtn(config.text.end);
        const queueBtn = findBtn(config.text.queuing);
        const skipHeavyQueueScan = queueBtn && PX._autoState.standbyMode &&
            (now - PX._autoState.highRankLastHeavyScan < config.highRankDomScanInterval);
        const pageText = skipHeavyQueueScan ? '' : getRankContextText();

        if (!PX._autoState.currentStuckLimit) {
            PX._autoState.currentStuckLimit = randomStuckLimitMs(config);
        }
        let queueDurationDisplay = "--";
        if (PX._autoState.qStart > 0) {
            queueDurationDisplay = PX.Utils.formatDurationMs(now - PX._autoState.qStart);
        }

        // ============================================================
        // State: END button visible (Operating)
        // ============================================================
        if (endBtn) {
            PX._autoState.qStart = 0;
            PX._autoState.standbyMode = false;

            if (!PX._autoState.isOp) {
                PX._autoState.isOp = true;
                PX._autoState.sessStart = now;
                console.log("[Stark HUD] >>> 操作开始");
                const currentCount = storage.get() + 1;
                notifier.notifyQueueSuccess(currentCount);
            }
            const durSec = Math.floor((now - PX._autoState.sessStart) / 1000);
            PX.Panel.updateUI(`正在操作 (${durSec}s)`, "已暂停", "--", "#00ff00", storage);
            document.title = `>>> 操作中 ${durSec}s <<<`;
            PX._autoState.lastMoveTime = now;
            PX._autoState.clickRetryCount = 0;
        }

        // ============================================================
        // State: QUEUE button visible (Queuing)
        // ============================================================
        else if (queueBtn) {
            if (PX._autoState.isOp) {
                const sessionDuration = now - PX._autoState.sessStart;
                PX._autoState.isOp = false;

                if (sessionDuration < config.minSessionTime) {
                    console.log(`[Stark HUD] 检测到异常操作：时长 ${Math.floor(sessionDuration/1000)}s < ${config.minSessionTime/1000}s`);
                    storage.addAnomaly();
                    PX.Panel.updateAnomalyUI(storage);

                    // Sync anomaly to controller
                    if (controller) {
                        const prevCount = storage.getConsecutiveAnomalies();
                        const newCount = prevCount + 1;
                        console.log(`[异常同步] 连续异常: ${prevCount} -> ${newCount}`);
                        storage.setConsecutiveAnomalies(newCount);

                        if (newCount >= controller.config.consecutiveAnomalyThreshold) {
                            console.log(`[异常同步] 🚨 连续异常达到 ${newCount} 次，触发自动退出！`);
                            controller.handleConsecutiveAnomalies();
                        }
                    }
                } else {
                    storage.add();
                    const successCount = storage.get();
                    const anomalyCount = storage.getAnomalyCount();
                    notifier.notifyOperationComplete(successCount, anomalyCount, {
                        duration: Math.floor(sessionDuration / 1000),
                        operationNum: successCount + anomalyCount
                    });
                    // Reset consecutive anomalies on success
                    storage.setConsecutiveAnomalies(0);
                }
            }

            if (PX.ArmSwitch.maybeSwitchToArenaArm(queueBtn, config, storage)) {
                setTimeout(() => loopWrapper(config, storage, notifier, controller), 1000);
                return;
            }

            if (!PX._autoState.qStart) {
                PX._autoState.qStart = now;
                PX._autoState.lastRawRank = -1;
                PX._autoState.rankWorseStreak = 0;
                PX._autoState.blindCount = 0;
                PX._autoState.lastMoveTime = now;
                PX._autoState.currentStuckLimit = randomStuckLimitMs(config);
                PX._autoState.requeueUsed = false;
            }
            PX._autoState.clickRetryCount = 0;

            if (skipHeavyQueueScan) {
                const cachedRank = PX._autoState.lastRawRank !== -1 ? PX._autoState.lastRawRank + 1 : "?";
                if (now - PX._autoState.highRankLastUiUpdate >= config.highRankLoopInterval) {
                    PX.Panel.updateUI(`静候模式: 排名 #${cachedRank}，低频扫描中...`, "省资源", queueDurationDisplay, "orange", storage);
                    document.title = `Standby #${cachedRank}`;
                    PX._autoState.highRankLastUiUpdate = now;
                }
                PX.Morning.updateWatchdogHeartbeat();
                setTimeout(() => loopWrapper(config, storage, notifier, controller), config.highRankLoopInterval);
                return;
            }
            PX._autoState.highRankLastHeavyScan = now;

            const rawRank = parseRawRank(pageText);
            const timerStrFromPage = getActiveTimerString(pageText);
            const realRank = rawRank !== null ? rawRank + 1 : null;

            if (realRank !== null && realRank > config.highRankStandbyThreshold) {
                if (!PX._autoState.standbyMode) {
                    console.log(`[Stark HUD] 进入静候模式：排名 #${realRank}`);
                    PX._autoState.standbyMode = true;
                    PX._autoState.highRankLastHeavyScan = now;
                    PX._autoState.highRankLastUiUpdate = 0;
                }
                if (now - PX._autoState.highRankLastUiUpdate >= config.highRankLoopInterval) {
                    PX.Panel.updateUI(`静候模式: 排名 #${realRank}，等待捡漏...`, "低频扫描", queueDurationDisplay, "orange", storage);
                    document.title = `Standby #${realRank}`;
                    PX._autoState.highRankLastUiUpdate = now;
                }
                PX._autoState.lastMoveTime = now;
                setTimeout(() => loopWrapper(config, storage, notifier, controller), config.highRankLoopInterval);
                return;
            }

            if (PX._autoState.standbyMode && realRank !== null && realRank <= config.highRankStandbyThreshold) {
                console.log(`[Stark HUD] 退出静候模式：排名回到 #${realRank}`);
                PX._autoState.standbyMode = false;
                PX._autoState.highRankLastUiUpdate = 0;
            }

            if (rawRank !== null) {
                PX._autoState.blindCount = 0;

                if (PX._autoState.morningRequeueActive) {
                    if (realRank > 100) {
                        if (!PX._autoState.morningExtraRequeueDone) {
                            PX._autoState.morningExtraRequeueDone = true;
                            PX.Panel.updateUI(`早八: 排名 #${realRank} > 100，二次重排`, "--", queueDurationDisplay, "#66ccff", storage);
                            PX.ArmSwitch.leaveQueueThenReenter(queueBtn, config);
                            PX._autoState.qStart = 0;
                            PX._autoState.lastRawRank = -1;
                            setTimeout(() => loopWrapper(config, storage, notifier, controller), 1000);
                            return;
                        } else {
                            PX._autoState.morningRequeueActive = false;
                        }
                    } else {
                        PX.Panel.updateUI(`早八成功: 第 ${realRank} 名`, "--", queueDurationDisplay, "#00ff99", storage);
                        PX._autoState.morningRequeueActive = false;
                    }
                }

                if (PX._autoState.lastRawRank !== -1 && rawRank > PX._autoState.lastRawRank + config.rankDropTolerance) {
                    PX._autoState.rankWorseStreak++;
                    if (PX._autoState.rankWorseStreak >= 2) {
                        PX.Morning.safeReload(`排名倒退: ${PX._autoState.lastRawRank + 1} -> ${realRank}`, notifier);
                        return;
                    }
                } else {
                    PX._autoState.rankWorseStreak = 0;
                }

                if (rawRank !== PX._autoState.lastRawRank) {
                    PX._autoState.lastRawRank = rawRank;
                    PX._autoState.lastMoveTime = now;
                    PX._autoState.currentStuckLimit = randomStuckLimitMs(config);
                }

                const stuckTime = now - PX._autoState.lastMoveTime;
                const timeLeftStr = PX.Utils.formatDurationMs(Math.max(0, PX._autoState.currentStuckLimit - stuckTime));

                if (rawRank <= config.safeZoneRawLimit) {
                    PX.Panel.updateUI(`决赛圈: 第 ${realRank} 名`, "坚守位置", queueDurationDisplay, "magenta", storage);
                    PX._autoState.lastMoveTime = now;
                } else {
                    const statusStr = timerStrFromPage ? `前车: ${timerStrFromPage} | 排名 #${realRank}` : `排队中: #${realRank}`;
                    const color = timerStrFromPage ? "#ffcc00" : "cyan";
                    PX.Panel.updateUI(statusStr, `${timeLeftStr} (超时刷新)`, queueDurationDisplay, color, storage);
                    if (stuckTime > PX._autoState.currentStuckLimit) {
                        PX.Morning.safeReload(`排名僵死 #${realRank}`, notifier);
                        return;
                    }
                }
                document.title = `Rank ${realRank}`;
            } else {
                PX._autoState.blindCount++;
                if (PX._autoState.morningRequeueActive) PX._autoState.morningRequeueActive = false;
                const stuckTime = now - PX._autoState.lastMoveTime;
                const timeLeftStr = PX.Utils.formatDurationMs(Math.max(0, PX._autoState.currentStuckLimit - stuckTime));
                const label = PX._autoState.blindCount >= 3 ? "盲排中..." : "读取队列中...";
                PX.Panel.updateUI(label, `${timeLeftStr} (超时刷新)`, queueDurationDisplay, "#aaaaaa", storage);
                if (PX._autoState.blindCount >= 3 && stuckTime > PX._autoState.currentStuckLimit) {
                    PX.Morning.safeReload("盲排超时", notifier);
                    return;
                }
            }

            const timerStr = getActiveTimerString(pageText);
            if (timerStr) {
                if (timerStr !== PX._autoState.lastTimerStr) {
                    PX._autoState.lastTimerStr = timerStr;
                    PX._autoState.lastTimerChangeTime = now;
                }
                else if (now - PX._autoState.lastTimerChangeTime > config.timerFreezeTimeout) {
                    PX.Morning.safeReload("倒计时卡死检测", notifier);
                    return;
                }
            }
        }

        // ============================================================
        // State: ENTER button visible (Can enter)
        // ============================================================
        else if (enterBtn) {
            if (PX._autoState.isOp) {
                const sessionDuration = now - PX._autoState.sessStart;
                PX._autoState.isOp = false;

                if (sessionDuration < config.minSessionTime) {
                    console.log(`[Stark HUD] 检测到异常操作：时长 ${Math.floor(sessionDuration/1000)}s < ${config.minSessionTime/1000}s`);
                    storage.addAnomaly();
                    PX.Panel.updateAnomalyUI(storage);

                    if (controller) {
                        const prevCount = storage.getConsecutiveAnomalies();
                        const newCount = prevCount + 1;
                        console.log(`[异常同步] 连续异常: ${prevCount} -> ${newCount}`);
                        storage.setConsecutiveAnomalies(newCount);

                        if (newCount >= controller.config.consecutiveAnomalyThreshold) {
                            console.log(`[异常同步] 🚨 连续异常达到 ${newCount} 次，触发自动退出！`);
                            controller.handleConsecutiveAnomalies();
                        }
                    }
                } else {
                    storage.add();
                    const successCount = storage.get();
                    const anomalyCount = storage.getAnomalyCount();
                    notifier.notifyOperationComplete(successCount, anomalyCount, {
                        duration: Math.floor(sessionDuration / 1000),
                        operationNum: successCount + anomalyCount
                    });
                    storage.setConsecutiveAnomalies(0);
                }
            }

            if (PX.ArmSwitch.maybeSwitchToArenaArm(null, config, storage)) {
                setTimeout(() => loopWrapper(config, storage, notifier, controller), 1000);
                return;
            }

            PX._autoState.qStart = 0;
            PX._autoState.lastMoveTime = now;
            PX._autoState.standbyMode = false;

            // Check anomaly cooldown
            if (controller) {
                const controllerState = controller.getState();
                if (controllerState.anomalyCooldownUntil && now < controllerState.anomalyCooldownUntil) {
                    const remainingMs = controllerState.anomalyCooldownUntil - now;
                    const remainingMin = Math.ceil(remainingMs / 60000);
                    PX.Panel.updateUI(`🔒 冷却期中：还剩 ${remainingMin} 分钟`, "--", "--", "orange", storage);
                    console.log(`[冷却期] 还剩 ${remainingMin} 分钟，不自动进入队列`);
                    setTimeout(() => loopWrapper(config, storage, notifier, controller), 1000);
                    return;
                }
            }

            if (!enterBtn._pScheduled) {
                PX._autoState.clickRetryCount++;
                const delay = PX.Utils.getRandomInt(config.clickDelayMin, config.clickDelayMax);
                enterBtn._pScheduled = true;
                PX.Panel.updateUI("发现目标信号", "--", "--", "yellow", storage);
                setTimeout(() => {
                    try {
                        enterBtn.click();
                        PX.Morning.updateWatchdogHeartbeat();
                    } catch (e) {
                        console.error(e);
                    } finally {
                        enterBtn._pScheduled = false;
                    }
                }, delay);
            }
        }

        // ============================================================
        // State: No buttons (Scanning)
        // ============================================================
        else {
            PX.Panel.updateUI("扫描信号中...", "--", "--", "#555555", storage);
            if (now - PX._autoState.lastMoveTime > config.fallbackReloadTimeout) {
                PX.Morning.safeReload("无信号超时", notifier);
                return;
            }
        }

        setTimeout(() => loopWrapper(config, storage, notifier, controller), 1000);
    }

    function loopWrapper(config, storage, notifier, controller) {
        try {
            loopUnsafe(config, storage, notifier, controller);
        } catch (e) {
            PX.Utils.recordScriptError('main.loop', e);
            setTimeout(() => loopWrapper(config, storage, notifier, controller), 1000);
        }
    }

    function scheduleLoop(delay, config, storage, notifier, controller) {
        PX._autoState.lastLoopDelay = delay;
        setTimeout(() => loopWrapper(config, storage, notifier, controller), delay);
    }

    // ============================================================
    // Exports
    // ============================================================
    PX.Automation = {
        findBtn: findBtn,
        isVisibleElement: isVisibleElement,
        getRankContextText: getRankContextText,
        parseRawRank: parseRawRank,
        getActiveTimerString: getActiveTimerString,
        loopUnsafe: loopUnsafe,
        loopWrapper: loopWrapper,
        scheduleLoop: scheduleLoop,
        start: function(config, storage, notifier, controller) {
            console.log('[Automation] Starting main loop in 3 seconds...');
            setTimeout(() => loopWrapper(config, storage, notifier, controller), 3000);
        }
    };
})();
