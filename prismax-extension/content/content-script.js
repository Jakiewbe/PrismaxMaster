// ============================================================
// PrismaX Extension - Content Script Entry Point
// Initializes all modules and starts the automation
// ============================================================
var PX = PX || {};

(async function() {
    'use strict';

    // Prevent duplicate initialization
    if (PX._initialized) return;
    PX._initialized = true;

    console.log('╔════════════════════════════════════════════╗');
    console.log('║   PRISMAX 跨端联动系统 v3.0 已加载        ║');
    console.log('╠════════════════════════════════════════════╣');
    console.log('║   ✅ Chrome Extension (Manifest V3)       ║');
    console.log('║   ✅ 通知系统就绪                          ║');
    console.log('║   ✅ 状态控制器就绪                        ║');
    console.log('║   ✅ HTTP Bridge 已启用                     ║');
    console.log('║   ✅ 性能优化已启用（静候模式降频）        ║');
    console.log('╚════════════════════════════════════════════╝');

    // ============================================================
    // Initialize storage
    // ============================================================
    await PX.StorageInit();
    console.log('[Init] Storage initialized');

    // ============================================================
    // Load configuration
    // ============================================================
    const cfg = await PX.Config.buildConfig();
    console.log('[Init] Config loaded');

    // Expose config for all modules
    PX._config = cfg.main;
    PX._controllerConfig = cfg.controller;
    PX._notifierConfig = cfg.notifier;
    PX._startDay = PX.Utils.getTodayStr();

    // ============================================================
    // Create notifier
    // ============================================================
    PX.Notifier = PX.createNotifier(cfg.notifier);
    console.log('[Init] Notifier created');

    // ============================================================
    // Create controller
    // ============================================================
    PX.Controller = PX.createController(cfg.controller, PX.Notifier);
    console.log('[Init] Controller created');

    // ============================================================
    // Set up shared state for automation modules
    // ============================================================
    PX._scriptPaused = false;
    PX._scriptPausedRef = { value: false }; // Mutable ref for panel toggle
    PX._loopHeartbeatAt = Date.now();
    PX._lastError = '';

    PX._autoState = {
        isOp: false,
        sessStart: 0,
        qStart: 0,
        lastRawRank: -1,
        rankWorseStreak: 0,
        blindCount: 0,
        lastMoveTime: Date.now(),
        currentStuckLimit: 0,
        lastTimerStr: null,
        lastTimerChangeTime: 0,
        clickRetryCount: 0,
        requeueUsed: false,
        morningRequeueActive: false,
        morningTriggeredAt: 0,
        morningExtraRequeueDone: false,
        armSwitchInProgress: false,
        standbyMode: false,
        highRankLastHeavyScan: 0,
        highRankLastUiUpdate: 0,
        lastLoopDelay: 1000
    };

    // ============================================================
    // Global error handlers
    // ============================================================
    window.addEventListener('error', (event) => {
        PX.Utils.recordScriptError('window.error', event.error || event.message);
    });

    window.addEventListener('unhandledrejection', (event) => {
        PX.Utils.recordScriptError('unhandledrejection', event.reason || 'Promise rejected');
    });

    // ============================================================
    // Message listeners (from service worker / popup)
    // ============================================================
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        try {
            switch (message.action) {
                case 'getState':
                    const controllerState = PX.Controller ? PX.Controller.getState() : {};
                    const perfInfo = PX.Controller ? PX.Controller.getPerformanceInfo() : {};
                    sendResponse({
                        controller: controllerState,
                        performance: perfInfo,
                        notifier: PX.Notifier ? PX.Notifier.getState() : {},
                        count: PX.Storage.get(),
                        anomaly: PX.Storage.getAnomalyCount(),
                        paused: PX._scriptPaused,
                        armSwitchDone: PX.Storage.isArmSwitchDone(),
                        commentTaskDone: PX.Storage.isCommentTaskDone(),
                        morningDone: PX.Storage.isMorningDone()
                    });
                    break;

                case 'togglePause':
                    PX._scriptPaused = !PX._scriptPaused;
                    PX._scriptPausedRef.value = PX._scriptPaused;
                    const toggleBtn = document.getElementById('st-toggle');
                    if (toggleBtn) {
                        toggleBtn.textContent = PX._scriptPaused ? "恢复脚本" : "暂停脚本";
                    }
                    sendResponse({ paused: PX._scriptPaused });
                    break;

                case 'resetStats':
                    if (PX.Controller) PX.Controller.resetStats();
                    PX.Storage.setCount(0);
                    PX.Storage.resetAnomaly();
                    PX.Storage.setConsecutiveAnomalies(0);
                    const c = document.getElementById('p-count');
                    if (c) c.innerText = "0";
                    PX.Panel.updateAnomalyUI(PX.Storage);
                    sendResponse({ success: true });
                    break;

                case 'testNotification':
                    if (PX.Notifier) PX.Notifier.sendTest();
                    sendResponse({ success: true });
                    break;

                case 'testConnection':
                    if (PX.Controller) PX.Controller.testConnection();
                    sendResponse({ success: true });
                    break;

                case 'resetCommentTask':
                    if (PX.CommentTask) PX.CommentTask.resetCommentTask(PX.Storage);
                    sendResponse({ success: true });
                    break;

                case 'MORNING_TRIGGER':
                    // From service worker: ensure morning routine
                    console.log('[Content] Received MORNING_TRIGGER from service worker');
                    sendResponse({ status: 'acknowledged' });
                    break;

                case 'COMMENT_TRIGGER':
                    console.log('[Content] Received COMMENT_TRIGGER from service worker');
                    sendResponse({ status: 'acknowledged' });
                    break;

                default:
                    sendResponse({ error: 'Unknown action' });
            }
        } catch (e) {
            console.error('[Content] Message handler error:', e);
            sendResponse({ error: e.message });
        }
        return true; // Keep channel open for async response
    });

    // ============================================================
    // Expose debugging APIs on window (for Console access)
    // ============================================================
    window.PX = PX;
    window.PrismAX = {
        getState: () => PX.Controller ? PX.Controller.getState() : null,
        getPerformance: () => PX.Controller ? PX.Controller.getPerformanceInfo() : null,
        testNotification: () => PX.Notifier ? PX.Notifier.sendTest() : null,
        testConnection: () => PX.Controller ? PX.Controller.testConnection() : null,
        getStorage: () => PX.Storage,
        resetCommentTask: () => PX.CommentTask ? PX.CommentTask.resetCommentTask(PX.Storage) : null,
        performCommentTask: () => PX.CommentTask ? PX.CommentTask.performCommentTask(PX._config, PX.Storage, PX.Notifier) : null,
        debugArmSwitch: () => PX.ArmSwitch ? PX.ArmSwitch.debugArenaArmSwitch(PX._config, PX.Storage) : null,
        togglePause: () => {
            PX._scriptPaused = !PX._scriptPaused;
            PX._scriptPausedRef.value = PX._scriptPaused;
            console.log('Script paused:', PX._scriptPaused);
        }
    };

    // ============================================================
    // Start everything
    // ============================================================
    function bootstrap() {
        // Start controller
        if (PX.Controller) PX.Controller.start();

        // Start main automation loop
        if (PX.Automation) PX.Automation.start(PX._config, PX.Storage, PX.Notifier, PX.Controller);

        console.log('[Init] All systems started');
    }

    // Wait for DOM to be ready (React SPA needs extra time)
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(bootstrap, 1000);
        });
    } else {
        setTimeout(bootstrap, 1000);
    }

    // ============================================================
    // Heartbeat for service worker tab tracking
    // ============================================================
    setInterval(async () => {
        try {
            await chrome.storage.local.set({ _tabHeartbeat: Date.now() });
        } catch (e) {}
    }, 10000);

    console.log('[Init] Content script ready');
})();
