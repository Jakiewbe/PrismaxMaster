// ============================================================
// PrismaX Extension - State Controller + HTTP Bridge + Performance
// Detects page state, pushes to Python Bridge, manages performance mode
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    function createController(config, notifier) {
        const CONFIG = config || {};

        const state = {
            isOperating: false,
            isQueuing: false,
            isStandby: true,
            sessionStartTime: 0,
            totalOperations: 0,
            anomalyCount: 0,
            consecutiveAnomalies: 0,
            anomalyCooldownUntil: 0,
            updateTimer: null,
            pushTimer: null,
            pushRetries: 0,
            lastPushTime: 0,
            lastPushSuccess: true,
            consecutivePushFailures: 0,
            isInStandbyMode: false,
            currentUpdateInterval: 500,
            currentPushInterval: 500,
            lastRank: null,
            loopHeartbeatAt: Date.now(),
            lastScriptError: '',
            pendingEventLogs: [],
            walletPopupActive: false,
            walletPopupLastSeen: 0
        };

        function log(...args) {
            console.log('[状态控制器]', ...args);
        }

        function queueEventLog(eventType, eventData) {
            state.pendingEventLogs.push({
                type: eventType,
                data: eventData,
                time: new Date().toISOString()
            });
            log(`[事件日志] 已排队: ${eventType}`);
        }

        function findButton(keywords) {
            const candidates = Array.from(document.querySelectorAll('button, div[role="button"]'));
            return candidates.find(el => {
                if (!el.offsetParent) return false;
                const text = el.innerText || el.textContent || '';
                return keywords.some(k => text.includes(k));
            });
        }

        function adjustPerformanceMode(rank) {
            if (!CONFIG.standbyEnabled) return;

            const shouldEnterStandby = rank !== null && rank > CONFIG.standbyRankThreshold;
            const wasInStandby = state.isInStandbyMode;

            if (shouldEnterStandby && !wasInStandby) {
                state.isInStandbyMode = true;
                state.currentUpdateInterval = CONFIG.standbyUpdateInterval;
                state.currentPushInterval = CONFIG.standbyPushInterval;

                console.log('[性能优化] ⚡ 进入静候模式（省电模式）');
                console.log(`   排名：#${rank} > ${CONFIG.standbyRankThreshold}`);
                console.log(`   检测间隔：${CONFIG.updateInterval}ms → ${CONFIG.standbyUpdateInterval}ms`);
                console.log(`   推送间隔：${CONFIG.pushInterval}ms → ${CONFIG.standbyPushInterval}ms`);

                restartTimers();
            }
            else if (!shouldEnterStandby && wasInStandby) {
                state.isInStandbyMode = false;
                state.currentUpdateInterval = CONFIG.updateInterval;
                state.currentPushInterval = CONFIG.pushInterval;

                console.log('[性能优化] ⚡ 退出静候模式（恢复正常频率）');
                if (rank !== null) {
                    console.log(`   排名：#${rank} ≤ ${CONFIG.standbyRankThreshold}`);
                }

                restartTimers();
            }

            state.lastRank = rank;
        }

        function restartTimers() {
            if (state.updateTimer) {
                clearInterval(state.updateTimer);
                state.updateTimer = null;
            }
            if (state.pushTimer) {
                clearInterval(state.pushTimer);
                state.pushTimer = null;
            }

            state.updateTimer = setInterval(() => {
                try {
                    detectPageState();
                    exportState();
                } catch (e) {
                    PX.Utils.recordScriptError('controller.updateTimer', e);
                }
            }, state.currentUpdateInterval);

            state.pushTimer = setInterval(() => {
                try {
                    const stateData = exportState();
                    pushStateToServer(stateData);
                } catch (e) {
                    PX.Utils.recordScriptError('controller.pushTimer', e);
                }
            }, state.currentPushInterval);

            log(`定时器已重启 - 检测:${state.currentUpdateInterval}ms, 推送:${state.currentPushInterval}ms`);
        }

        function detectPageState() {
            const endBtn = findButton(['End Tele-Operation', 'End Session']);
            const queueBtn = findButton(['Leave', 'Waiting', 'Position', 'Queued']);
            const enterBtn = findButton(['Enter', 'Start', 'Join']);

            const oldState = {
                isOperating: state.isOperating,
                isQueuing: state.isQueuing,
                isStandby: state.isStandby
            };

            if (endBtn) {
                state.isOperating = true;
                state.isQueuing = false;
                state.isStandby = false;

                if (!oldState.isOperating) {
                    onOperationStart();
                }

                adjustPerformanceMode(null);
            }
            else if (queueBtn) {
                state.isOperating = false;
                state.isQueuing = true;
                state.isStandby = false;

                if (oldState.isOperating) {
                    onOperationEnd();
                }

                const pageText = document.body.innerText || '';
                let rankMatch = pageText.match(/(\d{1,4})\s*(?:users?|people)\s+in\s+front/i);
                let rank = rankMatch ? parseInt(rankMatch[1], 10) + 1 : null;

                if (!rank) {
                    rankMatch = pageText.match(/Position[:\s]+(\d{1,4})/i);
                    rank = rankMatch ? parseInt(rankMatch[1], 10) : null;
                }

                if (!rank) {
                    rankMatch = pageText.match(/Queue[:\s]+(\d{1,4})/i);
                    rank = rankMatch ? parseInt(rankMatch[1], 10) : null;
                }

                adjustPerformanceMode(rank);
            }
            else if (enterBtn) {
                state.isOperating = false;
                state.isQueuing = false;
                state.isStandby = true;

                adjustPerformanceMode(null);
            }

            return state;
        }

        // Wallet popup detection (prevents OKX/MetaMask from stealing focus)
        function detectWalletPopup() {
            const now = Date.now();

            const walletIframes = document.querySelectorAll(
                'iframe[src*="okx"], iframe[src*="metamask"], iframe[src*="wallet"], ' +
                'iframe[id*="okx"], iframe[id*="wallet"], iframe[class*="wallet"]'
            );
            for (const iframe of walletIframes) {
                if (iframe.offsetParent) {
                    state.walletPopupActive = true;
                    state.walletPopupLastSeen = now;
                    console.log('[钱包检测] ⚠ 检测到钱包弹窗iframe:', iframe.src || iframe.id);
                    dismissWalletPopup();
                    return;
                }
            }

            const walletModals = document.querySelectorAll(
                '[class*="okx-wallet"], [class*="okxwallet"], ' +
                '[id*="okx-wallet"], [id*="okxwallet"], ' +
                '[class*="wallet-modal"], [class*="wallet-popup"], ' +
                'div[class*="web3modal"], div[class*="w3m"], ' +
                'w3m-modal, w3m-core-modal'
            );
            for (const modal of walletModals) {
                if (modal.offsetParent) {
                    state.walletPopupActive = true;
                    state.walletPopupLastSeen = now;
                    console.log('[钱包检测] ⚠ 检测到钱包弹窗元素:', modal.className || modal.id);
                    dismissWalletPopup();
                    return;
                }
            }

            const passwordInputs = document.querySelectorAll(
                'input[type="password"][placeholder*="password" i], ' +
                'input[type="password"][placeholder*="Password"], ' +
                'input[type="password"].wallet-password'
            );
            for (const input of passwordInputs) {
                if (input.offsetParent) {
                    const parent = input.closest('[class*="modal"], [class*="popup"], [class*="overlay"], [class*="dialog"], [role="dialog"]');
                    if (parent) {
                        state.walletPopupActive = true;
                        state.walletPopupLastSeen = now;
                        console.log('[钱包检测] ⚠ 检测到弹窗中的密码输入框');
                        dismissWalletPopup();
                        return;
                    }
                }
            }

            if (state.walletPopupActive && now - state.walletPopupLastSeen > 3000) {
                state.walletPopupActive = false;
                console.log('[钱包检测] ✅ 钱包弹窗已消失');
            }
        }

        function dismissWalletPopup() {
            try {
                const closeSelectors = [
                    'button[class*="close"]', 'button[aria-label*="Close"]',
                    'button[aria-label*="close"]', '[class*="close-btn"]',
                    '[class*="closeButton"]', 'button[class*="cancel"]',
                    'svg[class*="close"]', '[data-testid="close"]',
                    '.modal-close', '.popup-close'
                ];
                for (const sel of closeSelectors) {
                    const closeBtn = document.querySelector(sel);
                    if (closeBtn && closeBtn.offsetParent) {
                        closeBtn.click();
                        console.log('[钱包检测] 🔧 已点击关闭按钮:', sel);
                        return;
                    }
                }

                const overlays = document.querySelectorAll(
                    '[class*="overlay"], [class*="backdrop"], [class*="mask"], ' +
                    '[class*="Overlay"], [class*="Backdrop"]'
                );
                for (const overlay of overlays) {
                    if (overlay.offsetParent) {
                        overlay.click();
                        console.log('[钱包检测] 🔧 已点击遮罩层关闭弹窗');
                        return;
                    }
                }

                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
                document.dispatchEvent(new KeyboardEvent('keyup', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
                console.log('[钱包检测] 🔧 已发送Escape键尝试关闭弹窗');
            } catch (e) {
                console.warn('[钱包检测] 关闭弹窗失败:', e.message);
            }
        }

        function onOperationStart() {
            log('>>> 操作开始');
            state.sessionStartTime = Date.now();

            queueEventLog('operation_start', {
                operationCount: state.totalOperations + 1,
                timestamp: state.sessionStartTime
            });

            if (notifier) {
                const count = state.totalOperations + 1;
                notifier.notifyQueueSuccess(count);
            }
        }

        function onOperationEnd() {
            log('<<< 操作结束');

            const sessionDuration = Date.now() - state.sessionStartTime;
            const sessionDurationSec = Math.floor(sessionDuration / 1000);
            const minSessionTime = 40 * 1000;
            const minSessionTimeSec = 40;

            if (sessionDuration >= minSessionTime) {
                state.totalOperations++;
                state.consecutiveAnomalies = 0;
                log(`有效操作 +1，累计：${state.totalOperations}`);

                queueEventLog('operation_success', {
                    duration: sessionDurationSec,
                    totalOperations: state.totalOperations,
                    anomalyCount: state.anomalyCount
                });

                if (notifier) {
                    notifier.notifyOperationComplete(
                        state.totalOperations,
                        state.anomalyCount,
                        {
                            duration: sessionDurationSec,
                            operationNum: state.totalOperations + state.anomalyCount
                        }
                    );
                }
            } else {
                state.anomalyCount++;
                state.consecutiveAnomalies++;
                log(`异常操作 +1，累计：${state.anomalyCount}，连续：${state.consecutiveAnomalies}`);

                queueEventLog('operation_anomaly', {
                    duration: sessionDurationSec,
                    minRequired: minSessionTimeSec,
                    anomalyCount: state.anomalyCount,
                    consecutiveAnomalies: state.consecutiveAnomalies
                });

                if (notifier) {
                    notifier.notifyOperationAnomaly(
                        state.anomalyCount,
                        state.consecutiveAnomalies,
                        {
                            duration: sessionDurationSec,
                            minRequired: minSessionTimeSec,
                            operationNum: state.totalOperations + state.anomalyCount,
                            successCount: state.totalOperations
                        }
                    );
                }

                if (CONFIG.enableAnomalyAutoLeave &&
                    state.consecutiveAnomalies >= CONFIG.consecutiveAnomalyThreshold) {
                    log(`🚨 连续异常达到 ${state.consecutiveAnomalies} 次，触发自动退出！`);
                    handleConsecutiveAnomalies();
                }
            }

            state.sessionStartTime = 0;
        }

        function handleConsecutiveAnomalies() {
            const cooldownMs = CONFIG.anomalyCooldownMinutes * 60 * 1000;
            state.anomalyCooldownUntil = Date.now() + cooldownMs;
            log(`🔒 已设置冷却期：${CONFIG.anomalyCooldownMinutes} 分钟`);

            queueEventLog('consecutive_anomaly_triggered', {
                consecutiveCount: state.consecutiveAnomalies,
                cooldownMinutes: CONFIG.anomalyCooldownMinutes,
                cooldownUntil: state.anomalyCooldownUntil,
                totalAnomalies: state.anomalyCount,
                totalOperations: state.totalOperations
            });

            // Persist cooldown
            PX.Storage.setAnomalyCooldown(state.anomalyCooldownUntil);
            PX.Storage.setConsecutiveAnomalies(state.consecutiveAnomalies);

            if (notifier) {
                notifier.notifyConsecutiveAnomalies(
                    state.consecutiveAnomalies,
                    state.anomalyCount,
                    state.totalOperations,
                    CONFIG.anomalyCooldownMinutes
                );
            }

            const leaveBtn = findButton(['Leave', 'Exit']);
            if (leaveBtn) {
                console.log('[自动退出] 找到 Leave 按钮，正在退出排队...');
                try {
                    leaveBtn.click();
                    log('✅ 已点击 Leave 按钮，成功退出排队');
                    log(`⏰ 冷却期：${CONFIG.anomalyCooldownMinutes} 分钟内不会自动进入队列`);
                } catch (e) {
                    console.error('[自动退出] 点击按钮失败:', e);
                }
            } else {
                console.warn('[自动退出] ⚠️ 未找到 Leave 按钮');
            }

            state.consecutiveAnomalies = 0;
        }

        function exportState() {
            state.loopHeartbeatAt = PX._loopHeartbeatAt || Date.now();
            state.lastScriptError = PX._lastError || '';

            detectWalletPopup();

            const effectiveAllowOperation = state.isOperating && !state.walletPopupActive;

            const currentState = {
                timestamp: Date.now(),
                updateTime: new Date().toISOString(),
                allowOperation: effectiveAllowOperation,
                walletPopupActive: state.walletPopupActive,
                isOperating: state.isOperating,
                isQueuing: state.isQueuing,
                isStandby: state.isStandby,
                totalOperations: state.totalOperations,
                anomalyCount: state.anomalyCount,
                consecutiveAnomalies: state.consecutiveAnomalies,
                anomalyCooldownUntil: state.anomalyCooldownUntil,
                rank: state.lastRank,
                performanceMode: state.isInStandbyMode ? 'high_rank_standby' : 'normal',
                loopHeartbeatAt: state.loopHeartbeatAt,
                lastScriptError: state.lastScriptError,
                sessionStartTime: state.sessionStartTime,
                sessionDuration: state.sessionStartTime > 0
                    ? Math.floor((Date.now() - state.sessionStartTime) / 1000)
                    : 0,
                lastPushTime: state.lastPushTime,
                lastPushSuccess: state.lastPushSuccess,
                source: 'http'
            };

            if (CONFIG.enableLocalStorage) {
                try {
                    localStorage.setItem('prismax_state', JSON.stringify(currentState));
                } catch (e) {
                    console.error('[LocalStorage写入失败]', e);
                }
            }

            if (state.isOperating) {
                document.title = CONFIG.titleOperating;
            } else if (state.isQueuing) {
                document.title = CONFIG.titleQueuing;
            } else {
                document.title = CONFIG.titleStandby;
            }

            return currentState;
        }

        async function pushStateToServer(stateData) {
            if (!CONFIG.enablePush) return;

            try {
                const dataToSend = { ...stateData };
                if (state.pendingEventLogs.length > 0) {
                    dataToSend.eventLog = state.pendingEventLogs;
                    state.pendingEventLogs = [];
                }

                const response = await fetch(CONFIG.bridgeUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(dataToSend)
                });

                if (response.ok) {
                    const wasDisconnected = state.consecutivePushFailures >= CONFIG.maxRetries;

                    state.pushRetries = 0;
                    state.consecutivePushFailures = 0;
                    state.lastPushSuccess = true;
                    state.lastPushTime = Date.now();

                    if (wasDisconnected && notifier) {
                        notifier.notifyPythonReconnected();
                    }
                } else {
                    throw new Error(`HTTP ${response.status}`);
                }
            } catch (error) {
                state.lastPushSuccess = false;
                state.pushRetries++;
                state.consecutivePushFailures++;

                if (state.consecutivePushFailures === 1) {
                    console.error('[HTTP推送失败]', error.message);
                    console.warn('⚠️ 请确保 Bridge.py 中转服务已启动');
                }

                if (state.consecutivePushFailures >= CONFIG.maxRetries) {
                    if (state.consecutivePushFailures === CONFIG.maxRetries) {
                        console.error(`❌ 推送失败超过 ${CONFIG.maxRetries} 次，请检查中转服务`);
                        if (notifier) {
                            notifier.notifyBridgeDisconnected(state.consecutivePushFailures);
                        }
                    }
                }
            }
        }

        function start() {
            if (state.updateTimer) {
                log('已经在运行');
                return;
            }

            log('启动状态检测');
            queueEventLog('script_loaded', {
                loadedAt: Date.now(),
                userAgent: navigator.userAgent
            });
            queueEventLog('controller_started', { startedAt: Date.now() });

            // Restore cooldown from storage
            const savedCooldown = PX.Storage.getAnomalyCooldown();
            const savedConsecutive = PX.Storage.getConsecutiveAnomalies();

            if (savedCooldown > Date.now()) {
                state.anomalyCooldownUntil = savedCooldown;
                const remainingMin = Math.ceil((savedCooldown - Date.now()) / 60000);
                log(`🔒 恢复冷却期：还剩 ${remainingMin} 分钟`);
            } else if (savedCooldown > 0) {
                PX.Storage.clearAnomalyCooldown();
                PX.Storage.setConsecutiveAnomalies(0);
                log('冷却期已过期，已清理');
            }

            if (savedConsecutive > 0) {
                state.consecutiveAnomalies = savedConsecutive;
                log(`⚠️ 恢复连续异常计数：${state.consecutiveAnomalies}`);
            }

            state.currentUpdateInterval = CONFIG.updateInterval;
            state.currentPushInterval = CONFIG.pushInterval;

            state.updateTimer = setInterval(() => {
                try {
                    detectPageState();
                    exportState();
                } catch (e) {
                    PX.Utils.recordScriptError('controller.updateTimer', e);
                }
            }, state.currentUpdateInterval);

            state.pushTimer = setInterval(() => {
                try {
                    const stateData = exportState();
                    pushStateToServer(stateData);
                } catch (e) {
                    PX.Utils.recordScriptError('controller.pushTimer', e);
                }
            }, state.currentPushInterval);

            try {
                detectPageState();
                const initialState = exportState();
                pushStateToServer(initialState);
            } catch (e) {
                PX.Utils.recordScriptError('controller.initialState', e);
            }
        }

        function stop() {
            if (state.updateTimer) {
                clearInterval(state.updateTimer);
                state.updateTimer = null;
                log('状态检测已停止');
            }
            if (state.pushTimer) {
                clearInterval(state.pushTimer);
                state.pushTimer = null;
                log('推送循环已停止');
            }
        }

        function getState() {
            return {
                isOperating: state.isOperating,
                isQueuing: state.isQueuing,
                isStandby: state.isStandby,
                totalOperations: state.totalOperations,
                anomalyCount: state.anomalyCount,
                consecutiveAnomalies: state.consecutiveAnomalies,
                anomalyCooldownUntil: state.anomalyCooldownUntil,
                sessionDuration: state.sessionStartTime > 0
                    ? Math.floor((Date.now() - state.sessionStartTime) / 1000)
                    : 0,
                rank: state.lastRank,
                performanceMode: state.isInStandbyMode ? 'high_rank_standby' : 'normal',
                loopHeartbeatAt: state.loopHeartbeatAt,
                lastScriptError: state.lastScriptError,
                pushStatus: state.lastPushSuccess ? '✅ 正常' : '❌ 失败',
                pushRetries: state.pushRetries
            };
        }

        function getPerformanceInfo() {
            return {
                mode: state.isInStandbyMode ? '🔋 静候模式（省电）' : '⚡ 正常模式',
                isInStandbyMode: state.isInStandbyMode,
                updateInterval: state.currentUpdateInterval + 'ms',
                pushInterval: state.currentPushInterval + 'ms',
                resourceSaving: state.isInStandbyMode ? '~80%' : '0%',
                currentRank: state.lastRank,
                standbyThreshold: CONFIG.standbyRankThreshold
            };
        }

        function resetStats() {
            state.totalOperations = 0;
            state.anomalyCount = 0;
            state.consecutiveAnomalies = 0;
            state.anomalyCooldownUntil = 0;
            log('统计数据已重置（包括冷却期）');
        }

        function testConnection() {
            log('测试中转站连接...');
            const testData = { test: true, timestamp: Date.now() };
            pushStateToServer(testData).then(() => {
                if (state.lastPushSuccess) {
                    log('✅ 连接成功！中转站正常工作');
                    console.log('%c✅ Bridge 连接成功', 'color: #00ff00; font-weight: bold');
                } else {
                    log('❌ 连接失败，请检查 Bridge.py 是否运行');
                    console.log('%c❌ Bridge 连接失败', 'color: #ff0000; font-weight: bold');
                }
            });
        }

        return {
            config: CONFIG,
            start: start,
            stop: stop,
            getState: getState,
            detectPageState: detectPageState,
            resetStats: resetStats,
            exportState: exportState,
            testConnection: testConnection,
            getPerformanceInfo: getPerformanceInfo,
            handleConsecutiveAnomalies: handleConsecutiveAnomalies,
            queueEventLog: queueEventLog,
            // Expose state for automation module
            _state: state
        };
    }

    PX.createController = createController;
})();
