// ============================================================
// PrismaX Extension - Morning Trigger ("早八协议")
// Daily 08:01-08:06 scheduled queue reset with watchdog
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    // Shared state for morning module
    const morning = {
        lock: false,
        watchdogLastHeartbeat: Date.now(),
        watchdogTimer: null,
        inMorningWindow: false
    };

    function updateWatchdogHeartbeat() {
        morning.watchdogLastHeartbeat = Date.now();
    }

    function startMorningWatchdog(config, storage) {
        if (morning.watchdogTimer) return;
        if (!config.morningWatchdogEnabled) return;

        morning.watchdogTimer = setInterval(() => {
            if (morning.inMorningWindow) {
                const elapsed = Date.now() - morning.watchdogLastHeartbeat;
                if (elapsed > config.morningWatchdogTimeout) {
                    console.log('[早八看门狗] 页面假死检测，准备刷新...');
                    PX.Notifier.notifyError('早八看门狗：页面假死检测');
                    setTimeout(() => { location.reload(); }, 1000);
                }
            }
        }, config.morningWatchdogCheckInterval);
    }

    function stopMorningWatchdog() {
        if (morning.watchdogTimer) {
            clearInterval(morning.watchdogTimer);
            morning.watchdogTimer = null;
        }
    }

    function safeReload(reason, notifier) {
        if (notifier) notifier.notifyError(reason);
        console.log(`[Stark HUD] 即将刷新: ${reason}`);
        setTimeout(() => { location.reload(); }, 2000);
    }

    function getMorningWindowMs(config) {
        if (!config.morningEnabled) return null;
        const start = PX.Utils.parseTimeToday(config.morningWindowStart);
        const end = PX.Utils.parseTimeToday(config.morningWindowEnd);
        if (!start || !end) return null;
        const startMs = start.getTime();
        const endMs = end.getTime();
        if (!(endMs > startMs)) return null;
        return { startMs, endMs };
    }

    function updateMorningInfo(config, storage) {
        const info = document.getElementById('p-morning-info');
        if (!info) return;
        if (!config.morningEnabled) { info.style.display = 'none'; return; }
        const win = getMorningWindowMs(config);
        if (!win) { info.style.display = 'none'; return; }

        info.style.display = '';
        const now = Date.now();
        const { startMs, endMs } = win;

        if (storage.isMorningDone() || PX._autoState.morningTriggeredAt) {
            info.innerHTML = "✓ 早八协议已完成";
            return;
        }
        if (now > endMs) {
            info.innerHTML = "今日早八窗口已结束";
            return;
        }

        const targetMs = storage.getMorningTarget();
        if (config.morningRandomInsideWindow) {
            if (!targetMs) {
                if (now < startMs) {
                    const timeStr = new Date(startMs).toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
                    info.innerHTML = `早八窗口 ${timeStr} 开启`;
                } else {
                    info.innerHTML = "正在生成触发时间点...";
                }
            } else {
                if (now < startMs) {
                    const timeStr = new Date(targetMs).toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
                    info.innerHTML = `⏰ 早八目标: ${timeStr}`;
                } else if (now >= startMs && now <= endMs) {
                    if (now < targetMs) {
                        const countdown = PX.Utils.formatDurationMs(targetMs - now);
                        const timeStr = new Date(targetMs).toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
                        info.innerHTML = `⏳ 倒计时 ${countdown} (目标 ${timeStr})`;
                    } else {
                        info.innerHTML = "⚡ 正在触发早八协议...";
                    }
                }
            }
        } else {
            if (now < startMs) {
                const countdown = PX.Utils.formatDurationMs(startMs - now);
                info.innerHTML = `⏳ 早八倒计时: ${countdown}`;
            } else {
                info.innerHTML = "⚡ 正在触发早八协议...";
            }
        }
    }

    function performMorningRequeue(config, storage, notifier) {
        if (morning.lock) return;
        morning.lock = true;
        setTimeout(() => { morning.lock = false; }, 1000);

        console.log("[Stark HUD] 执行早八协议检查...");
        updateWatchdogHeartbeat();

        if (PX._scriptPaused) {
            console.log("[Stark HUD] 早八被跳过（脚本暂停）");
            return;
        }

        const queueBtn = findBtn(config.text.queuing);
        const enterBtn = findBtn(config.text.enter);

        if (!queueBtn && !enterBtn) {
            console.log("[Stark HUD] 早八触发时刻，但未检测到按钮！等待下一秒重试...");
            PX.Panel.updateUI("早八: 按钮未刷新，等待中...", "--", "--", "#ff3333", storage);
            return;
        }

        console.log("[Stark HUD] 发现按钮，触发点击！重置计数！");
        notifier.notifyMorningTrigger();

        storage.setCount(0);
        storage.resetAnomaly();
        const c = document.getElementById('p-count');
        if (c) c.innerText = "0";
        PX.Panel.updateAnomalyUI(storage);

        PX._autoState.morningTriggeredAt = Date.now();
        storage.markMorningDone();
        PX._autoState.morningRequeueActive = true;
        PX._autoState.morningExtraRequeueDone = false;

        if (queueBtn) {
            if (config.armSwitchTask.morningReturnToGold) {
                if (PX.ArmSwitch && PX.ArmSwitch.returnToTrainingGold) {
                    PX.ArmSwitch.returnToTrainingGold(queueBtn, config, storage, notifier);
                }
                return;
            }
            PX.Panel.updateUI("早八: 正在重置连接...", "--", "--", "#66ccff", storage);
            if (PX.ArmSwitch) PX.ArmSwitch.leaveQueueThenReenter(queueBtn, config);
            PX._autoState.qStart = 0; PX._autoState.lastRawRank = -1;
        } else if (enterBtn) {
            PX.Panel.updateUI("早八: 建立新连接...", "--", "--", "#66ccff", storage);
            try { enterBtn.click(); } catch (e) { console.error(e); }
            updateWatchdogHeartbeat();
        }
    }

    // Helper: find button by keywords
    function findBtn(keywords) {
        const enterKeys = PX._config && PX._config.text ? PX._config.text.enter : [];
        const blacklist = PX._config && PX._config.text ? PX._config.text.blacklist : [];
        return PX.Utils.findClickableByKeywords(keywords, {
            blacklist: blacklist,
            excludeLeave: keywords === enterKeys
        });
    }

    // Check if currently in morning window
    function isInMorningWindow() {
        return morning.inMorningWindow;
    }
    function setInMorningWindow(v) {
        morning.inMorningWindow = v;
    }

    PX.Morning = {
        updateWatchdogHeartbeat: updateWatchdogHeartbeat,
        startMorningWatchdog: startMorningWatchdog,
        stopMorningWatchdog: stopMorningWatchdog,
        safeReload: safeReload,
        getMorningWindowMs: getMorningWindowMs,
        updateMorningInfo: updateMorningInfo,
        performMorningRequeue: performMorningRequeue,
        findBtn: findBtn,
        isInMorningWindow: isInMorningWindow,
        setInMorningWindow: setInMorningWindow,
        _morning: morning
    };
})();
