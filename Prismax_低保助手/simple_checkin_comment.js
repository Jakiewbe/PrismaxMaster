// ==UserScript==
// @name        PrismaX 低保助手 - 简化版签到和评论
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  简化版：只包含签到和评论功能，去除所有复杂逻辑
// @author       PrismaX Team
// @match        https://app.prismax.ai/*
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    // ================= 配置区域 =================
    // 注意：配置已移至 simple_config.js，如需修改请编辑该文件
    let CONFIG = {
        morningEnabled: true,
        morningWindowStart: "08:01",
        morningWindowEnd: "08:06",
        morningRandomInsideWindow: true,
        morningIgnoreDone: false,
        requeueDelayMs: 2000,

        commentTask: {
            enabled: true,
            windowStart: "00:00",
            windowEnd: "00:05",
            randomInsideWindow: true,
            commentCount: { min: 5, max: 5 },
            commentDelay: { min: 5000, max: 8000 },
            retryCount: 3,
            retryDelay: 2000,
            comments: [
                "PrismaX demonstrates an exceptional integration of Web3 automation, intelligent execution logic, and user-centric design, making it one of the most forward-looking and practically useful AI agents in the decentralized ecosystem today.",
                "What truly sets PrismaX apart is not only its technical robustness, but also its ability to translate complex on-chain operations into reliable, scalable, and fully autonomous decision-making workflows.",
                "PrismaX is redefining how users interact with decentralized systems by combining strategic intelligence, execution efficiency, and a remarkably intuitive automation framework into a single coherent product.",
                "In an ecosystem full of experimental tools, PrismaX stands out as a production-grade, mission-critical AI agent infrastructure that can genuinely support long-term, large-scale Web3 operations.",
                "The architectural design of PrismaX reflects a deep understanding of both blockchain mechanics and real-world automation needs, resulting in a system that is powerful, flexible, and surprisingly easy to deploy.",
                "By bridging intelligent agents with decentralized finance and on-chain execution, PrismaX is not merely a tool, but a foundational layer for the next generation of autonomous Web3 applications."
            ]
        },

        text: {
            enter: ["Enter Live Control", "Join Queue", "Enter Pool"],
            queuing: ["Leave", "Waiting", "Position", "Queued"],
            liveChat: ["Live Chat", "Open Live Chat"],
            queue: ["Queue"]
        }
    };

    // 尝试加载外部配置文件（如果存在）
    try {
        const script = document.createElement('script');
        script.src = 'https://raw.githubusercontent.com/your-repo/simple_config.js'; // 用户可替换为实际路径
        script.onerror = () => console.log('[低保助手] 未找到外部配置文件，使用默认配置');
        document.head.appendChild(script);
    } catch (e) {
        console.log('[低保助手] 使用内置配置');
    }

    // ================= 存储键名 =================
    const STORAGE_KEYS = {
        MORNING_DONE: 'simple_morning_done',
        MORNING_TARGET: 'simple_morning_target',
        MORNING_PRERELOAD: 'simple_morning_prereload',
        COMMENT_TASK_DONE: 'simple_comment_task_done',
        COMMENT_TASK_TARGET: 'simple_comment_task_target',
        COMMENT_IN_PROGRESS: 'simple_comment_in_progress'
    };

    // ================= 工具函数 =================
    function getTodayStr() {
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    }

    function getRandomInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    function parseTimeToday(hm) {
        if (!hm || typeof hm !== 'string') return null;
        const parts = hm.split(':');
        if (parts.length < 2) return null;
        const h = Number(parts[0]);
        const m = Number(parts[1]);
        if (isNaN(h) || isNaN(m)) return null;
        const now = new Date();
        return new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m, 0, 0);
    }

    function findBtn(keywords) {
        const candidates = Array.from(document.querySelectorAll('button, div[role="button"], span'));
        return candidates.find(el => {
            if (!el.offsetParent) return false;
            const txt = el.innerText.trim();
            if (!txt) return false;
            const lower = txt.toLowerCase();
            return keywords.some(k => lower.includes(k.toLowerCase()));
        });
    }

    function findTabBtn(keywords) {
        const selectors = [
            'button',
            'div[role="button"]',
            'span',
            '[class*="tab"]'
        ];
        const allElements = document.querySelectorAll(selectors.join(', '));
        const candidates = Array.from(allElements);
        
        return candidates.find(el => {
            if (!el.offsetParent) return false;
            const txt = (el.innerText || el.textContent || '').trim();
            if (!txt) return false;
            return keywords.some(k => {
                return txt.toLowerCase() === k.toLowerCase() || 
                       txt.toLowerCase().includes(k.toLowerCase());
            });
        });
    }

    function isVisibleElement(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function findExactVisibleButton(labels) {
        const normalized = labels.map(label => label.toLowerCase());
        const candidates = Array.from(document.querySelectorAll('button, div[role="button"]'));
        return candidates.find(el => {
            if (!isVisibleElement(el)) return false;
            const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
            return normalized.includes(txt);
        });
    }

    function confirmLeaveQueueIfPresent() {
        let confirmBtn = document.querySelector('button[class*="leaveModalConfirmBtn"], .QueuePanel_leaveModalConfirmBtn__ZtiIr');
        if (confirmBtn && !isVisibleElement(confirmBtn)) confirmBtn = null;
        if (!confirmBtn) confirmBtn = findExactVisibleButton(['Leave queue', 'Leave Queue']);
        if (!confirmBtn) return false;
        try {
            confirmBtn.click();
            console.log('[签到] 已确认离开队列弹窗');
            return true;
        } catch (e) {
            console.error('[签到] 点击 Leave queue 确认失败:', e);
            return false;
        }
    }

    function clickEnterAfterLeave() {
        const enter = findBtn(CONFIG.text.enter);
        if (enter) {
            try {
                enter.click();
                console.log('[签到] 已重新进入队列');
            } catch (e) {
                console.error('[签到] 点击Enter按钮失败:', e);
            }
        } else {
            console.log('[签到] 未找到重新进入按钮，等待下轮扫描');
        }
    }

    function waitConfirmThenEnter(attempt = 0) {
        if (confirmLeaveQueueIfPresent()) {
            setTimeout(clickEnterAfterLeave, CONFIG.requeueDelayMs);
            return;
        }
        if (attempt >= 10) {
            console.log('[签到] 未检测到离队确认弹窗，尝试直接重新进入');
            setTimeout(clickEnterAfterLeave, CONFIG.requeueDelayMs);
            return;
        }
        setTimeout(() => waitConfirmThenEnter(attempt + 1), 250);
    }

    function leaveQueueThenReenter(queueBtn) {
        try {
            queueBtn.click();
        } catch (e) {
            console.error('[签到] 点击Queue按钮失败:', e);
        }

        setTimeout(() => waitConfirmThenEnter(0), 250);
    }

    // ================= 签到功能 =================
    function hasMorningDoneToday() {
        if (CONFIG.morningIgnoreDone) return false;
        return localStorage.getItem(STORAGE_KEYS.MORNING_DONE) === getTodayStr();
    }

    function markMorningDoneToday() {
        console.log('[签到] 标记今日早八已完成');
        localStorage.setItem(STORAGE_KEYS.MORNING_DONE, getTodayStr());
    }

    function hasMorningPreReloadToday() {
        return localStorage.getItem(STORAGE_KEYS.MORNING_PRERELOAD) === getTodayStr();
    }

    function markMorningPreReloadToday() {
        localStorage.setItem(STORAGE_KEYS.MORNING_PRERELOAD, getTodayStr());
    }

    function getMorningTarget() {
        const val = localStorage.getItem(STORAGE_KEYS.MORNING_TARGET);
        return val ? parseInt(val, 10) : 0;
    }

    function setMorningTarget(ts) {
        localStorage.setItem(STORAGE_KEYS.MORNING_TARGET, String(ts));
    }

    function getMorningWindowMs() {
        if (!CONFIG.morningEnabled) return null;
        const start = parseTimeToday(CONFIG.morningWindowStart);
        const end = parseTimeToday(CONFIG.morningWindowEnd);
        if (!start || !end) return null;
        const startMs = start.getTime();
        const endMs = end.getTime();
        if (!(endMs > startMs)) return null;
        return { startMs, endMs };
    }

    function performMorningRequeue() {
        console.log('[签到] 执行早八签到...');
        
        const queueBtn = findBtn(CONFIG.text.queuing);
        const enterBtn = findBtn(CONFIG.text.enter);

        if (!queueBtn && !enterBtn) {
            console.log('[签到] 未检测到按钮，等待重试...');
            return;
        }

        console.log('[签到] 发现按钮，触发点击！');
        markMorningDoneToday();

        if (queueBtn) {
            leaveQueueThenReenter(queueBtn);
        } else if (enterBtn) {
            try {
                enterBtn.click();
            } catch (e) {
                console.error('[签到] 点击Enter按钮失败:', e);
            }
        }
    }

    // ================= 评论功能 =================
    function isCommentTaskDone() {
        return localStorage.getItem(STORAGE_KEYS.COMMENT_TASK_DONE) === getTodayStr();
    }

    function markCommentTaskDone() {
        localStorage.setItem(STORAGE_KEYS.COMMENT_TASK_DONE, getTodayStr());
    }

    function isCommentInProgress() {
        return localStorage.getItem(STORAGE_KEYS.COMMENT_IN_PROGRESS) === 'true';
    }

    function setCommentInProgress(v) {
        localStorage.setItem(STORAGE_KEYS.COMMENT_IN_PROGRESS, v ? 'true' : 'false');
    }

    function getCommentTarget() {
        const val = localStorage.getItem(STORAGE_KEYS.COMMENT_TASK_TARGET);
        return val ? parseInt(val, 10) : 0;
    }

    function setCommentTarget(ts) {
        localStorage.setItem(STORAGE_KEYS.COMMENT_TASK_TARGET, String(ts));
    }

    function getCommentWindowMs() {
        if (!CONFIG.commentTask.enabled) return null;
        const start = parseTimeToday(CONFIG.commentTask.windowStart);
        const end = parseTimeToday(CONFIG.commentTask.windowEnd);
        if (!start || !end) return null;
        const startMs = start.getTime();
        const endMs = end.getTime();
        if (!(endMs > startMs)) return null;
        return { startMs, endMs };
    }

    async function sendOneComment(comment, retryCount = 0) {
        const maxRetries = CONFIG.commentTask.retryCount;
        const retryDelay = CONFIG.commentTask.retryDelay;

        try {
            // 检查界面是否收起
            let openLiveChatBtn = document.querySelector('button[class*="TeleOpRightPanel_openBtnDesktop"]');
            if (!openLiveChatBtn) {
                openLiveChatBtn = Array.from(document.querySelectorAll('button, div, span'))
                    .find(el => (el.innerText || '').trim().includes('Open Live Chat'));
            }
            if (openLiveChatBtn) {
                console.log('[评论] 界面已收起，重新展开...');
                openLiveChatBtn.click();
                await new Promise(r => setTimeout(r, 1500));
            }
            
            // 查找输入框
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
            
            if (!input) {
                console.error('[评论] 未找到输入框');
                if (retryCount < maxRetries) {
                    console.log(`[评论] 重试 ${retryCount + 1}/${maxRetries}...`);
                    await new Promise(r => setTimeout(r, retryDelay));
                    return sendOneComment(comment, retryCount + 1);
                }
                return false;
            }

            // 输入评论（React 兼容方式）
            input.focus();
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(input, comment);
            const inputEvent = new Event('input', { bubbles: true });
            input.dispatchEvent(inputEvent);
            
            console.log(`[评论] 已输入内容: "${comment.substring(0, 30)}..."`);
            await new Promise(r => setTimeout(r, 2000));

            // 查找并点击发送按钮
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
                const allBtns = document.querySelectorAll('button');
                sendBtn = Array.from(allBtns).find(btn => {
                    const svg = btn.querySelector('svg');
                    return svg && btn.offsetParent;
                });
            }
            
            if (sendBtn) {
                sendBtn.focus();
                await new Promise(r => setTimeout(r, 100));
                sendBtn.click();
                console.log(`[评论] 已点击发送按钮`);
            } else {
                console.log(`[评论] 未找到发送按钮，尝试 Enter 键...`);
                input.dispatchEvent(new KeyboardEvent('keydown', { 
                    key: 'Enter', keyCode: 13, bubbles: true 
                }));
            }
            
            await new Promise(r => setTimeout(r, 2000));
            console.log(`[评论] ✅ 已发送: "${comment.substring(0, 30)}..."`);
            return true;
        } catch (e) {
            console.error('[评论] 发送错误:', e);
            if (retryCount < maxRetries) {
                console.log(`[评论] 重试 ${retryCount + 1}/${maxRetries}...`);
                await new Promise(r => setTimeout(r, retryDelay));
                return sendOneComment(comment, retryCount + 1);
            }
            return false;
        }
    }

    async function performCommentTask() {
        console.log('[评论任务] 检查状态...');
        
        if (isCommentTaskDone()) {
            console.log('[评论任务] 今日任务已完成，跳过');
            return;
        }
        
        if (isCommentInProgress()) {
            console.log('[评论任务] 任务正在进行中，跳过');
            return;
        }

        console.log('[评论任务] === 开始执行评论任务 ===');
        setCommentInProgress(true);

        let successCount = 0;
        
        try {
            // Step 1: 点击 Live Chat 标签
            let liveChatBtn = null;
            
            // 方法1: 使用CSS类名选择器
            try {
                const tabButtons = document.querySelectorAll('button[class*="TeleOpRightPanel_tab"]');
                liveChatBtn = Array.from(tabButtons).find(el => (el.innerText || '').trim() === 'Live Chat');
            } catch (e) {
                console.log('[评论任务] 方法1 出错:', e.message);
            }
            
            // 方法2: 精确匹配文字
            if (!liveChatBtn) {
                try {
                    const allElements = Array.from(document.querySelectorAll('button, span, div'));
                    liveChatBtn = allElements.find(el => {
                        const txt = (el.innerText || el.textContent || '').trim();
                        return txt === 'Live Chat';
                    });
                } catch (e) {
                    console.log('[评论任务] 方法2 出错:', e.message);
                }
            }
            
            // 方法3: 使用findTabBtn
            if (!liveChatBtn) {
                try {
                    liveChatBtn = findTabBtn(CONFIG.text.liveChat);
                } catch (e) {
                    console.log('[评论任务] 方法3 出错:', e.message);
                }
            }
            
            if (!liveChatBtn) {
                console.error('[评论任务] ❌ 未找到 Live Chat 按钮，任务终止');
                setCommentInProgress(false);
                return;
            }
            
            liveChatBtn.click();
            console.log('[评论任务] ✅ 已点击 Live Chat');
            await new Promise(r => setTimeout(r, 2000));

            // Step 2: 发送评论
            const commentCount = getRandomInt(CONFIG.commentTask.commentCount.min, CONFIG.commentTask.commentCount.max);
            const comments = CONFIG.commentTask.comments;
            const usedIndices = [];

            for (let i = 0; i < commentCount; i++) {
                try {
                    // 随机选择一条未使用的评论
                    let idx;
                    do {
                        idx = getRandomInt(0, comments.length - 1);
                    } while (usedIndices.includes(idx) && usedIndices.length < comments.length);
                    usedIndices.push(idx);

                    const comment = comments[idx];
                    const success = await sendOneComment(comment);
                    if (success) successCount++;
                    
                    console.log(`[评论任务] 进度: ${i + 1}/${commentCount}，成功: ${successCount}`);

                    // 评论间隔
                    if (i < commentCount - 1) {
                        const delay = getRandomInt(CONFIG.commentTask.commentDelay.min, CONFIG.commentTask.commentDelay.max);
                        console.log(`[评论任务] 等待 ${delay}ms 后发送下一条...`);
                        await new Promise(r => setTimeout(r, delay));
                    }
                } catch (commentError) {
                    console.error(`[评论任务] 第 ${i + 1} 条评论发送失败:`, commentError.message);
                }
            }

            console.log(`[评论任务] ✅ 已发送 ${successCount}/${commentCount} 条评论`);

            // Step 3: 返回 Queue
            await new Promise(r => setTimeout(r, 1000));
            
            try {
                let openBtn = document.querySelector('button[class*="TeleOpRightPanel_openBtnDesktop"]');
                if (openBtn) {
                    console.log('[评论任务] 界面已收起，点击展开...');
                    openBtn.click();
                    await new Promise(r => setTimeout(r, 1500));
                }
                
                let queueBtn = Array.from(document.querySelectorAll('button[class*="TeleOpRightPanel_tab"]'))
                    .find(el => (el.innerText || '').trim() === 'Queue');
                
                if (!queueBtn) {
                    queueBtn = findTabBtn(CONFIG.text.queue);
                }
                
                if (queueBtn) {
                    queueBtn.click();
                    console.log('[评论任务] ✅ 已返回 Queue');
                }
            } catch (queueError) {
                console.log('[评论任务] ⚠️ 返回 Queue 失败:', queueError.message);
            }

            // 标记任务完成
            if (successCount > 0) {
                markCommentTaskDone();
                console.log('[评论任务] === 评论任务完成 ===');
            } else {
                console.log('[评论任务] === 评论任务失败，稍后可重试 ===');
            }
            
        } catch (e) {
            console.error('[评论任务] ❌ 执行错误:', e);
        } finally {
            setCommentInProgress(false);
        }
    }

    // ================= 主循环 =================
    function mainLoop() {
        if (!document.body) {
            setTimeout(mainLoop, 1000);
            return;
        }

        const now = Date.now();
        const currentDay = getTodayStr();

        // 签到功能检查
        if (CONFIG.morningEnabled) {
            const morningWin = getMorningWindowMs();
            
            // 早八前预刷新
            if (morningWin && !hasMorningDoneToday() && !hasMorningPreReloadToday()) {
                const { startMs } = morningWin;
                if (now >= startMs - 60000 && now < startMs) {
                    console.log('[签到] 触发早八前预刷新');
                    markMorningPreReloadToday();
                    window.location.reload();
                    return;
                }
            }

            // 早八签到
            if (morningWin && !hasMorningDoneToday()) {
                const { startMs, endMs } = morningWin;
                if (CONFIG.morningRandomInsideWindow) {
                    let targetMs = getMorningTarget();
                    if (!targetMs || targetMs < startMs || targetMs > endMs) {
                        targetMs = getRandomInt(startMs, endMs - 1);
                        setMorningTarget(targetMs);
                        console.log('[签到] 生成并保存早八时间:', new Date(targetMs).toLocaleTimeString());
                    }
                    if (now >= targetMs && now <= endMs) {
                        performMorningRequeue();
                    }
                } else {
                    if (now >= startMs && now <= endMs) {
                        performMorningRequeue();
                    }
                }
            }
        }

        // 评论功能检查
        if (CONFIG.commentTask.enabled) {
            const commentWin = getCommentWindowMs();
            if (commentWin && !isCommentTaskDone() && !isCommentInProgress()) {
                const { startMs, endMs } = commentWin;
                if (CONFIG.commentTask.randomInsideWindow) {
                    let targetMs = getCommentTarget();
                    if (!targetMs || targetMs < startMs || targetMs > endMs) {
                        targetMs = getRandomInt(startMs, endMs - 1);
                        setCommentTarget(targetMs);
                        console.log('[评论任务] 生成并保存执行时间:', new Date(targetMs).toLocaleTimeString());
                    }
                    if (now >= targetMs && now <= endMs) {
                        performCommentTask();
                    }
                } else {
                    if (now >= startMs && now <= endMs) {
                        performCommentTask();
                    }
                }
            }
        }

        // 每5秒检查一次
        setTimeout(mainLoop, 5000);
    }

    // ================= 启动 =================
    console.log('[低保助手] 简化版签到和评论脚本已加载');
    console.log('[低保助手] 签到时间窗口:', CONFIG.morningWindowStart, '-', CONFIG.morningWindowEnd);
    console.log('[低保助手] 评论时间窗口:', CONFIG.commentTask.windowStart, '-', CONFIG.commentTask.windowEnd);
    
    // 等待页面加载完成后启动
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mainLoop);
    } else {
        mainLoop();
    }

})();
