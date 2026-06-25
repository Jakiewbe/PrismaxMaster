// ============================================================
// PrismaX Extension - Comment Task
// Auto-post comments in Live Chat during 00:00-00:05 window
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    function getCommentWindowMs(config) {
        if (!config.commentTask || !config.commentTask.enabled) return null;
        const start = PX.Utils.parseTimeToday(config.commentTask.windowStart);
        const end = PX.Utils.parseTimeToday(config.commentTask.windowEnd);
        if (!start || !end) return null;
        const startMs = start.getTime();
        const endMs = end.getTime();
        if (!(endMs > startMs)) return null;
        return { startMs, endMs };
    }

    function findTabBtn(keywords) {
        const found = PX.Utils.findClickableByKeywords(keywords);
        console.log(`[评论任务] 搜索标签: ${keywords.join(', ')}，结果: ${found ? '找到' : '未找到'}`);

        if (!found) {
            console.log('[评论任务] ⚠️ 未找到匹配标签，列出可点击元素:');
            Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]'))
                .filter(PX.Utils.isVisibleElement)
                .slice(0, 20)
                .forEach((el, i) => {
                const txt = PX.Utils.getElementText(el).substring(0, 30);
                if (txt) console.log(`   ${i}: "${txt}"`);
            });
        }

        return found;
    }

    async function sendOneComment(comment, config, retryCount) {
        if (retryCount === undefined) retryCount = 0;
        const maxRetries = config.commentTask.retryCount;
        const retryDelay = config.commentTask.retryDelay;

        try {
            // Check if chat panel is collapsed, expand it
            let openLiveChatBtn = document.querySelector('button[class*="TeleOpRightPanel_openBtnDesktop"]');
            if (!openLiveChatBtn) {
                openLiveChatBtn = Array.from(document.querySelectorAll('button, div, span'))
                    .find(el => PX.Utils.isVisibleElement(el) && PX.Utils.getElementText(el).includes('Open Live Chat'));
            }
            if (openLiveChatBtn) {
                console.log('[评论任务] 检测到界面已收起，重新展开...');
                openLiveChatBtn.click();
                await new Promise(r => setTimeout(r, 1500));
            }

            // Find input field
            let input = document.querySelector('input[placeholder*="Send" i], input[placeholder*="chat" i], input[placeholder*="message" i]');
            if (!input) {
                input = document.querySelector('textarea[placeholder*="Send" i], textarea[placeholder*="chat" i]');
            }
            if (!input) {
                input = document.querySelector('input[class*="LiveChatModule"], input[class*="messageInput"]');
            }
            if (!input) {
                const allInputs = document.querySelectorAll('input, textarea');
                input = Array.from(allInputs).find(el => {
                    const ph = (el.placeholder || '').toLowerCase();
                    return ph.includes('send') || ph.includes('chat') || ph.includes('message');
                });
            }

            console.log('[评论任务] 输入框搜索结果:', input);

            if (!input) {
                console.error('[评论任务] ❌ 未找到输入框');
                if (retryCount < maxRetries) {
                    console.log(`[评论任务] 重试 ${retryCount + 1}/${maxRetries}...`);
                    await new Promise(r => setTimeout(r, retryDelay));
                    return sendOneComment(comment, config, retryCount + 1);
                }
                return false;
            }

            // React-compatible input
            input.focus();

            const proto = input instanceof HTMLTextAreaElement
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            nativeInputValueSetter.call(input, comment);

            const inputEvent = new Event('input', { bubbles: true });
            input.dispatchEvent(inputEvent);

            console.log(`[评论任务] 📝 已输入内容: "${comment.substring(0, 30)}..."`);

            // Wait for input to register
            await new Promise(r => setTimeout(r, 2000));

            // Find and click send button
            console.log(`[评论任务] 🖱️ 查找并点击发送按钮...`);

            let sendBtn = document.querySelector('button[class*="LiveChatModule_sendButton"]');
            if (!sendBtn) {
                sendBtn = document.querySelector('button[type="submit"]');
            }
            if (!sendBtn) {
                const inputParent = input.closest('div, form');
                if (inputParent) {
                    sendBtn = inputParent.querySelector('button');
                }
            }
            if (!sendBtn) {
                const allBtns = Array.from(document.querySelectorAll('button'));
                sendBtn = allBtns.find(b => {
                    if (!PX.Utils.isVisibleElement(b)) return false;
                    const txt = PX.Utils.getElementText(b).toLowerCase();
                    return txt.includes('send') || txt.includes('发送') ||
                           (b.querySelector('svg') && b.offsetWidth < 80);
                });
            }

            if (sendBtn) {
                sendBtn.click();
                console.log('[评论任务] ✅ 已点击发送按钮');
            } else {
                // Fallback: press Enter
                console.log('[评论任务] 未找到发送按钮，使用Enter键发送');
                input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            }

            await new Promise(r => setTimeout(r, 500));
            return true;

        } catch (error) {
            console.error('[评论任务] 发送评论异常:', error);
            if (retryCount < config.commentTask.retryCount) {
                await new Promise(r => setTimeout(r, config.commentTask.retryDelay));
                return sendOneComment(comment, config, retryCount + 1);
            }
            return false;
        }
    }

    async function performCommentTask(config, storage, notifier) {
        if (!config.commentTask || !config.commentTask.enabled) return;

        // Check if already done today
        if (storage.isCommentTaskDone()) return;

        // Check if already in progress (and not timed out)
        if (storage.isCommentInProgress() && !storage.isCommentTaskTimeout()) {
            return;
        }

        // If timed out, reset
        if (storage.isCommentInProgress() && storage.isCommentTaskTimeout()) {
            console.log('[评论任务] 检测到超时，重置状态');
            await storage.resetCommentTaskState();
        }

        const comments = config.commentTask.comments;
        const countCfg = config.commentTask.commentCount;
        const delayCfg = config.commentTask.commentDelay;
        const commentCount = PX.Utils.getRandomInt(countCfg.min, countCfg.max);

        console.log(`[评论任务] ========== 开始执行评论任务 ==========`);
        console.log(`[评论任务] 计划发送 ${commentCount} 条评论`);

        // Set in progress
        await storage.setCommentInProgress(true);
        PX.Panel.updateCommentTaskUI(storage);

        // Store start time for timeout detection
        const startTime = Date.now();

        try {
            // Step 1: Click "Live Chat" tab
            console.log('[评论任务] 步骤1: 查找并点击 Live Chat 标签...');

            const liveChatClicked = await clickLiveChatTab(config);

            if (!liveChatClicked) {
                console.error('[评论任务] ❌ 无法找到 Live Chat 标签，任务中止');
                return;
            }

            // Step 2: Send comments
            console.log(`[评论任务] 步骤2: 发送 ${commentCount} 条评论...`);

            let successCount = 0;
            // Shuffle and pick comments
            const shuffled = [...comments].sort(() => Math.random() - 0.5);
            const selected = shuffled.slice(0, commentCount);

            for (let i = 0; i < selected.length; i++) {
                const comment = selected[i];
                console.log(`[评论任务] 发送评论 ${i + 1}/${selected.length}: "${comment.substring(0, 30)}..."`);

                const ok = await sendOneComment(comment, config);

                if (ok) successCount++;

                // Random delay between comments
                if (i < selected.length - 1) {
                    const delay = PX.Utils.getRandomInt(delayCfg.min, delayCfg.max);
                    console.log(`[评论任务] 等待 ${delay}ms 后发送下一条...`);
                    await new Promise(r => setTimeout(r, delay));
                }
            }

            console.log(`[评论任务] 评论发送完成：成功 ${successCount}/${selected.length}`);

            // Step 3: Return to Queue tab
            console.log('[评论任务] 步骤3: 返回 Queue 标签...');
            const queueKeywords = config.text.queue || ['Queue'];
            const queueTab = findTabBtn(queueKeywords);
            if (queueTab) {
                queueTab.click();
                console.log('[评论任务] ✅ 已点击 Queue 标签');
            }

            // Mark as done if at least one comment succeeded
            if (successCount > 0) {
                await storage.markCommentTaskDone();

                // Log to controller
                if (PX.Controller && PX.Controller.queueEventLog) {
                    PX.Controller.queueEventLog('comment_task_complete', {
                        successCount: successCount,
                        total: selected.length,
                        duration: Math.floor((Date.now() - startTime) / 1000)
                    });
                }

                if (notifier) {
                    notifier.notifyCommentTaskComplete(successCount);
                }
            }

        } catch (error) {
            console.error('[评论任务] 执行异常:', error);
            if (PX.Controller && PX.Controller.queueEventLog) {
                PX.Controller.queueEventLog('comment_task_failed', {
                    error: error.message,
                    duration: Math.floor((Date.now() - startTime) / 1000)
                });
            }
        } finally {
            // Clean up
            if (storage.isCommentInProgress()) {
                await storage.setCommentInProgress(false);
            }
            PX.Panel.updateCommentTaskUI(storage);
            console.log(`[评论任务] ========== 任务结束 ==========`);
        }
    }

    async function clickLiveChatTab(config) {
        const keywords = config.text.liveChat || ['Live Chat', 'Open Live Chat'];

        // Method 0: Exact class match
        let tab = document.querySelector('button[class*="TeleOpRightPanel_tab"]');
        if (tab) {
            const txt = PX.Utils.getElementText(tab);
            if (txt === 'Live Chat' || txt.toLowerCase().includes('live chat')) {
                console.log('[评论任务] 方法0: 通过精确类名找到 Live Chat 标签');
                tab.click();
                await new Promise(r => setTimeout(r, 1000));
                return true;
            }
        }

        // Method 1: Exact text match on buttons
        const allBtns = Array.from(document.querySelectorAll('button, span, div'));
        tab = allBtns.find(el => {
            if (!PX.Utils.isVisibleElement(el)) return false;
            const txt = PX.Utils.getElementText(el);
            return txt === 'Live Chat' || txt === 'Open Live Chat';
        });
        if (tab) {
            console.log('[评论任务] 方法1: 通过精确文本匹配找到 Live Chat 标签');
            tab.click();
            await new Promise(r => setTimeout(r, 1000));
            return true;
        }

        // Method 2: Find Queue button first, then find Live Chat sibling
        const queueBtn = Array.from(document.querySelectorAll('button')).find(el => {
            if (!PX.Utils.isVisibleElement(el)) return false;
            const txt = PX.Utils.getElementText(el);
            return txt === 'Queue';
        });
        if (queueBtn) {
            const parent = queueBtn.parentElement;
            if (parent) {
                const siblings = Array.from(parent.querySelectorAll('button, span, div'));
                tab = siblings.find(el => {
                    if (!PX.Utils.isVisibleElement(el)) return false;
                    const txt = PX.Utils.getElementText(el);
                    return txt === 'Live Chat' || txt === 'Open Live Chat';
                });
                if (tab) {
                    console.log('[评论任务] 方法2: 通过兄弟元素找到 Live Chat 标签');
                    tab.click();
                    await new Promise(r => setTimeout(r, 1000));
                    return true;
                }
            }
        }

        // Method 3: Fallback to keyword search
        tab = findTabBtn(keywords);
        if (tab) {
            console.log('[评论任务] 方法3: 通过关键词找到 Live Chat 标签');
            tab.click();
            await new Promise(r => setTimeout(r, 1000));
            return true;
        }

        console.error('[评论任务] 所有方法均未找到 Live Chat 标签');
        return false;
    }

    // Expose for testing
    function resetCommentTask(storage) {
        storage.resetCommentTaskState();
        PX.Panel.updateCommentTaskUI(storage);
        console.log('[评论任务] 状态已手动重置');
    }

    PX.CommentTask = {
        getCommentWindowMs: getCommentWindowMs,
        findTabBtn: findTabBtn,
        sendOneComment: sendOneComment,
        performCommentTask: performCommentTask,
        resetCommentTask: resetCommentTask
    };
})();
