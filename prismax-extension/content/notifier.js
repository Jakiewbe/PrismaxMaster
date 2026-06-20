// ============================================================
// PrismaX Extension - Notification System
// Multi-channel push notifications: PushDeer, WeCom, ServerChan, Telegram
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    function createNotifier(config) {
        const CONFIG = config || {};

        const state = {
            lastNotificationTime: {},
            totalSent: 0,
            totalFailed: 0
        };

        const LEVEL = {
            INFO: 'INFO',
            SUCCESS: 'SUCCESS',
            WARNING: 'WARNING',
            CRITICAL: 'CRITICAL'
        };

        const ICONS = {
            INFO: '🎉',
            SUCCESS: '✅',
            WARNING: '⚠️',
            CRITICAL: '🚨'
        };

        function log(...args) {
            if (CONFIG.debug) console.log('[PRISMAX通知]', ...args);
        }

        function formatTime() {
            return new Date().toLocaleString('zh-CN', {
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit', second: '2-digit',
                hour12: false
            });
        }

        function checkCooldown(key, force) {
            if (force) return true;
            const now = Date.now();
            const lastTime = state.lastNotificationTime[key] || 0;
            const elapsed = (now - lastTime) / 1000;
            if (elapsed < CONFIG.cooldown) {
                log(`冷却中，${Math.ceil(CONFIG.cooldown - elapsed)}秒后可再次发送`);
                return false;
            }
            return true;
        }

        function updateCooldown(key) {
            state.lastNotificationTime[key] = Date.now();
        }

        function send(title, content, level, force) {
            if (!level) level = LEVEL.INFO;
            if (!force) force = false;
            const notificationKey = `${level}:${title}`;
            if (!checkCooldown(notificationKey, force)) return;

            const icon = ICONS[level] || '📬';
            const fullTitle = `${icon} ${title}`;
            const fullContent = `${content}\n\n⏰ ${formatTime()}`;

            updateCooldown(notificationKey);
            sendAsync(fullTitle, fullContent, level);
        }

        async function sendAsync(title, content, level) {
            log(`发送通知: ${title}`);
            try {
                let success = false;
                switch (CONFIG.type) {
                    case 'pushdeer': success = await sendPushDeer(title, content); break;
                    case 'wecom': success = await sendWeCom(title, content); break;
                    case 'serverchan': success = await sendServerChan(title, content); break;
                    case 'telegram': success = await sendTelegram(title, content); break;
                }
                if (success) {
                    state.totalSent++;
                    log(`✓ 发送成功`);
                } else {
                    state.totalFailed++;
                    log(`✗ 发送失败`);
                }
            } catch (error) {
                state.totalFailed++;
                log(`✗ 发送异常:`, error);
            }
        }

        async function sendPushDeer(title, content) {
            const key = CONFIG.pushdeer.key;
            if (!key || key === 'PDU123XXX') {
                log('PushDeer Key 未配置');
                return false;
            }
            try {
                const formData = new FormData();
                formData.append('pushkey', key);
                formData.append('text', title);
                formData.append('desp', content);
                formData.append('type', 'markdown');
                const response = await fetch(CONFIG.pushdeer.api, { method: 'POST', body: formData });
                const result = await response.json();
                return result.code === 0;
            } catch (error) {
                log('PushDeer 错误:', error);
                return false;
            }
        }

        async function sendWeCom(title, content) {
            const webhook = CONFIG.wecom.webhook;
            if (!webhook) return false;
            try {
                const data = { msgtype: 'markdown', markdown: { content: `## ${title}\n\n${content}` }};
                const response = await fetch(webhook, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                return result.errcode === 0;
            } catch (error) {
                return false;
            }
        }

        async function sendServerChan(title, content) {
            const key = CONFIG.serverchan.key;
            if (!key) return false;
            try {
                const url = `${CONFIG.serverchan.api}/${key}.send`;
                const formData = new FormData();
                formData.append('title', title);
                formData.append('desp', content);
                const response = await fetch(url, { method: 'POST', body: formData });
                const result = await response.json();
                return result.code === 0;
            } catch (error) {
                return false;
            }
        }

        async function sendTelegram(title, content) {
            const token = CONFIG.telegram.botToken;
            const chatId = CONFIG.telegram.chatId;
            if (!token || !chatId) return false;
            try {
                const url = `${CONFIG.telegram.api}/bot${token}/sendMessage`;
                const text = `<b>${title}</b>\n\n${content}`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' })
                });
                const result = await response.json();
                return result.ok === true;
            } catch (error) {
                return false;
            }
        }

        // --- Notification helpers ---
        function notifyQueueSuccess(count) {
            send('🎯 开始操作',
                `📍 第 ${count} 次操作开始\n\n` +
                `⏰ 开始时间：${formatTime()}`,
                LEVEL.INFO);
        }

        function notifyOperationComplete(successCount, anomalyCount, details) {
            details = details || {};
            const total = successCount + anomalyCount;
            const rate = total > 0 ? (successCount / total * 100).toFixed(1) : 0;
            const duration = details.duration || 0;
            const operationNum = details.operationNum || successCount;

            let content = `📍 第 ${operationNum} 次操作完成\n`;
            content += `⏱️ 操作时长：${duration} 秒\n\n`;
            content += `📊 今日统计：\n`;
            content += `   ✅ 成功：${successCount} 次\n`;
            content += `   ❌ 异常：${anomalyCount} 次\n`;
            content += `   📈 成功率：${rate}%`;

            send('✅ 操作完成', content, LEVEL.SUCCESS);
        }

        function notifyOperationAnomaly(anomalyCount, consecutiveCount, details) {
            details = details || {};
            const duration = details.duration || 0;
            const minRequired = details.minRequired || 40;
            const operationNum = details.operationNum || 0;
            const successCount = details.successCount || 0;
            const total = successCount + anomalyCount;
            const rate = total > 0 ? (successCount / total * 100).toFixed(1) : 0;

            let content = `📍 第 ${operationNum} 次操作异常\n\n`;
            content += `❓ 异常原因：操作时间过短\n`;
            content += `   实际时长：${duration} 秒\n`;
            content += `   最低要求：${minRequired} 秒\n\n`;
            content += `⚠️ 连续异常：${consecutiveCount} 次\n`;
            if (consecutiveCount >= 2) {
                content += `   （达到阈值将自动退出排队）\n`;
            }
            content += `\n📊 今日统计：\n`;
            content += `   ✅ 成功：${successCount} 次\n`;
            content += `   ❌ 异常：${anomalyCount} 次\n`;
            content += `   📈 成功率：${rate}%`;

            send('⚠️ 操作异常', content, LEVEL.WARNING, true);
        }

        function notifyError(reason) {
            console.log(`[通知系统] 页面刷新: ${reason} (不推送)`);
        }

        function notifyMorningTrigger() {
            send('🌅 早八协议触发',
                `✅ 已重置队列，正在重新排队\n\n` +
                `⏰ 触发时间：${formatTime()}`,
                LEVEL.INFO, true);
        }

        function notifyConsecutiveAnomalies(count, totalAnomalies, successCount, cooldownMinutes) {
            const total = successCount + totalAnomalies;
            const rate = total > 0 ? (successCount / total * 100).toFixed(1) : 0;

            let content = `🚨 检测到连续 ${count} 次操作异常\n`;
            content += `✋ 已自动退出排队\n\n`;
            content += `🔒 冷却期：${cooldownMinutes} 分钟\n`;
            content += `   （期间不会自动进入队列）\n\n`;
            content += `📊 今日统计：\n`;
            content += `   ✅ 成功：${successCount} 次\n`;
            content += `   ❌ 异常：${totalAnomalies} 次\n`;
            content += `   📈 成功率：${rate}%\n\n`;
            content += `💡 建议：检查网络连接或 Python 端状态`;

            send('🛑 连续异常警告', content, LEVEL.CRITICAL, true);
        }

        function notifyBridgeDisconnected(failCount) {
            send('🔌 Python 端断连',
                `❌ 连续 ${failCount} 次无法连接 Python 端\n\n` +
                `⚠️ 影响：\n` +
                `   • 键盘操作将停止执行\n` +
                `   • 操作可能被判定为异常\n\n` +
                `💡 解决方案：\n` +
                `   1. 检查 Bridge_v2.py 是否运行\n` +
                `   2. 检查 prismax_bot 是否运行\n` +
                `   3. 检查端口 5000 是否被占用\n\n` +
                `⏰ 时间：${formatTime()}`,
                LEVEL.CRITICAL, true);
        }

        function notifyPythonReconnected() {
            send('✅ Python 端已重连',
                `🔗 与 Python 端的连接已恢复\n\n` +
                `⏰ 时间：${formatTime()}`,
                LEVEL.SUCCESS, true);
        }

        function notifyCommentTaskComplete(commentCount) {
            send('💬 评论任务完成',
                `✅ 已成功在 Live Chat 发送 ${commentCount} 条评论\n\n` +
                `⏰ 完成时间：${formatTime()}`,
                LEVEL.SUCCESS, true);
        }

        function sendTest() {
            send('测试通知',
                `如果你收到这条消息，说明通知系统配置成功！\n\n配置类型: ${CONFIG.type}\n时间: ${formatTime()}`,
                LEVEL.INFO, true);
            log('测试通知已发送，请检查手机');
        }

        function getState() {
            return {
                totalSent: state.totalSent,
                totalFailed: state.totalFailed,
                type: CONFIG.type
            };
        }

        return {
            send: send,
            notifyQueueSuccess: notifyQueueSuccess,
            notifyOperationComplete: notifyOperationComplete,
            notifyOperationAnomaly: notifyOperationAnomaly,
            notifyError: notifyError,
            notifyMorningTrigger: notifyMorningTrigger,
            notifyConsecutiveAnomalies: notifyConsecutiveAnomalies,
            notifyBridgeDisconnected: notifyBridgeDisconnected,
            notifyPythonReconnected: notifyPythonReconnected,
            notifyCommentTaskComplete: notifyCommentTaskComplete,
            sendTest: sendTest,
            getState: getState,
            LEVEL: LEVEL,
            get config() { return CONFIG; }
        };
    }

    PX.createNotifier = createNotifier;
})();
