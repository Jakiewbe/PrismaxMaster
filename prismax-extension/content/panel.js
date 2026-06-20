// ============================================================
// PrismaX Extension - UI Panel (HUD overlay)
// Floating status panel with drag support, styled like Stark UI
// ============================================================
var PX = PX || {};

(function() {
    'use strict';

    function injectStyles() {
        if (document.getElementById('prismax-panel-styles')) return;
        const css = `
            @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;700&display=swap');
            #stark-panel {
                position: fixed; bottom: 30px; right: 30px; width: 320px;
                background: rgba(10, 20, 35, 0.95);
                clip-path: polygon(15px 0, 100% 0, 100% calc(100% - 15px), calc(100% - 15px) 100%, 0 100%, 0 15px);
                border: 2px solid rgba(0, 243, 255, 0.5);
                box-shadow: 0 0 15px rgba(0, 243, 255, 0.3), inset 0 0 20px rgba(0, 243, 255, 0.1);
                color: #00f3ff; font-family: 'Rajdhani', 'Arial', sans-serif;
                z-index: 999999; padding: 12px 14px;
                backdrop-filter: blur(8px); transition: all 0.3s ease;
            }
            #stark-panel:hover {
                box-shadow: 0 0 25px rgba(0, 243, 255, 0.5), inset 0 0 30px rgba(0, 243, 255, 0.2);
                border-color: rgba(0, 243, 255, 0.8);
            }
            .st-header {
                display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 10px; padding-bottom: 8px;
                border-bottom: 1px solid rgba(0, 243, 255, 0.3); cursor: move;
            }
            .st-title {
                font-weight: 700; font-size: 13px; letter-spacing: 1.2px;
                text-transform: uppercase; text-shadow: 0 0 8px rgba(0, 243, 255, 0.8);
            }
            .st-header-right { display: flex; align-items: center; gap: 8px; }
            .st-arc-reactor {
                width: 14px; height: 14px; background: #00f3ff; border-radius: 50%;
                box-shadow: 0 0 10px #00f3ff, 0 0 20px #00f3ff, inset 0 0 5px #fff;
                animation: reactor-pulse 2s infinite ease-in-out;
            }
            @keyframes reactor-pulse {
                0% { opacity: 0.6; box-shadow: 0 0 5px #00f3ff; }
                50% { opacity: 1; box-shadow: 0 0 15px #00f3ff, 0 0 25px #00f3ff; }
                100% { opacity: 0.6; box-shadow: 0 0 5px #00f3ff; }
            }
            .st-collapse-btn {
                font-size: 10px; cursor: pointer; padding: 3px 6px;
                border: 1px solid rgba(0, 243, 255, 0.4);
                border-radius: 2px; text-transform: uppercase;
                transition: all 0.2s; color: #00f3ff;
            }
            .st-collapse-btn:hover {
                background: rgba(0, 243, 255, 0.1);
                border-color: rgba(0, 243, 255, 0.6);
            }
            .st-status-box {
                background: rgba(0, 243, 255, 0.08);
                border: 1px solid rgba(0, 243, 255, 0.4);
                border-radius: 4px;
                padding: 8px 12px; margin-bottom: 10px;
                font-size: 13px; font-weight: 600;
                text-shadow: 0 0 5px currentColor;
                text-align: center;
                transition: all 0.3s;
            }
            .st-data-section {
                background: rgba(0, 0, 0, 0.2);
                border-radius: 4px;
                padding: 8px 10px;
                margin-bottom: 8px;
            }
            .st-row {
                display: flex; justify-content: space-between;
                margin-bottom: 6px; font-size: 12px; align-items: center;
                padding: 2px 0;
            }
            .st-row:last-child { margin-bottom: 0; }
            .st-label {
                color: rgba(255, 255, 255, 0.65);
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.8px;
                font-weight: 500;
            }
            .st-value {
                font-weight: 700;
                font-size: 13px;
                text-align: right;
            }
            .st-val-cyan { color: #00f3ff; text-shadow: 0 0 8px rgba(0, 243, 255, 0.6); }
            .st-val-gold { color: #ffd700; text-shadow: 0 0 8px rgba(255, 215, 0, 0.6); }
            .st-val-gray { color: #8899aa; }
            .st-val-orange { color: #ff9966; text-shadow: 0 0 8px rgba(255, 153, 102, 0.6); }
            .st-morning-info {
                font-size: 11px;
                color: #00f3ff;
                margin-top: 6px;
                padding: 6px 8px;
                background: rgba(0, 243, 255, 0.05);
                border-left: 3px solid rgba(0, 243, 255, 0.5);
                border-radius: 2px;
                letter-spacing: 0.5px;
                line-height: 1.4;
            }
            .st-footer {
                margin-top: 8px; padding-top: 8px;
                border-top: 1px solid rgba(255, 215, 0, 0.2);
                font-size: 11px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .st-footer-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .st-count-display {
                color: rgba(255, 255, 255, 0.7);
                font-size: 11px;
            }
            .st-count-display b {
                color: #fff;
                text-shadow: 0 0 5px #fff;
                font-size: 14px;
                margin: 0 3px;
            }
            .st-button-group {
                display: flex;
                gap: 6px;
            }
            #st-reset, #st-toggle {
                cursor: pointer;
                padding: 4px 8px;
                border: 1px solid rgba(255, 215, 0, 0.3);
                border-radius: 3px;
                transition: all 0.2s;
                text-transform: uppercase;
                font-size: 10px;
                background: rgba(0, 0, 0, 0.2);
                color: #ffd700;
            }
            #st-reset:hover, #st-toggle:hover {
                background: rgba(255, 215, 0, 0.2);
                box-shadow: 0 0 10px rgba(255, 215, 0, 0.5);
                color: #fff;
                border-color: rgba(255, 215, 0, 0.6);
            }
        `;
        const style = document.createElement('style');
        style.id = 'prismax-panel-styles';
        style.textContent = css;
        document.head.appendChild(style);
    }

    function createPanel(storage, scriptPausedRef) {
        if (document.getElementById('stark-panel')) return;
        injectStyles();

        const p = document.createElement('div');
        p.id = 'stark-panel';
        p.innerHTML = `
            <div class="st-header" id="st-header">
                <span class="st-title">PRISMAX 无忧助手 V3.0</span>
                <div class="st-header-right">
                    <span class="st-collapse-btn" id="st-collapse">折叠</span>
                    <div class="st-arc-reactor" id="st-indicator"></div>
                </div>
            </div>
            <div id="st-body">
                <div id="st-status" class="st-status-box st-val-cyan">贾维斯系统初始化...</div>

                <div class="st-data-section">
                    <div class="st-row">
                        <span class="st-label">自动刷新倒数</span>
                        <span id="p-timer" class="st-value st-val-cyan">--</span>
                    </div>
                    <div class="st-row">
                        <span class="st-label">当前排队时长</span>
                        <span id="p-duration" class="st-value st-val-gold">0m 0s</span>
                    </div>
                    <div class="st-row">
                        <span class="st-label">异常操作次数</span>
                        <span id="p-anomaly" class="st-value st-val-orange">0 次</span>
                    </div>
                    <div class="st-row">
                        <span class="st-label">评论任务</span>
                        <span id="p-comment-task" class="st-value st-val-gray">未完成</span>
                    </div>
                </div>

                <div id="p-morning-info" class="st-morning-info"></div>

                <div class="st-footer">
                    <div class="st-footer-row">
                        <span class="st-count-display">今日战绩: <b id="p-count">0</b> 次有效操作</span>
                    </div>
                    <div class="st-footer-row">
                        <div class="st-button-group">
                            <span id="st-toggle">暂停脚本</span>
                            <span id="st-reset">重置协议</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(p);

        // Restore panel position from storage
        const savedX = storage.getPanelPosX();
        const savedY = storage.getPanelPosY();
        if (savedX !== null && savedY !== null) {
            p.style.left = `${parseInt(savedX, 10)}px`;
            p.style.top = `${parseInt(savedY, 10)}px`;
            p.style.right = 'auto'; p.style.bottom = 'auto';
        }

        // Restore collapsed state
        const collapsed = storage.isPanelCollapsed();
        const body = document.getElementById('st-body');
        const collapseBtn = document.getElementById('st-collapse');
        if (collapsed && body && collapseBtn) {
            body.style.display = 'none';
            collapseBtn.textContent = '展开';
        }

        // Reset button
        const resetBtn = document.getElementById('st-reset');
        if (resetBtn) resetBtn.onclick = () => storage.reset();

        // Pause/Resume toggle button
        const toggleBtn = document.getElementById('st-toggle');
        if (toggleBtn) {
            toggleBtn.onclick = () => {
                scriptPausedRef.value = !scriptPausedRef.value;
                toggleBtn.textContent = scriptPausedRef.value ? "恢复脚本" : "暂停脚本";
            };
        }

        // Collapse/Expand button
        if (collapseBtn) {
            collapseBtn.onclick = (e) => {
                e.stopPropagation();
                if (!body) return;
                const isHidden = body.style.display === 'none';
                body.style.display = isHidden ? '' : 'none';
                collapseBtn.textContent = isHidden ? '折叠' : '展开';
                storage.setPanelCollapsed(!isHidden);
            };
        }

        // Drag handling
        const header = document.getElementById('st-header');
        if (header) {
            let isDragging = false, offsetX = 0, offsetY = 0;
            header.addEventListener('mousedown', (e) => {
                if (e.target.id === 'st-collapse') return;
                isDragging = true;
                const rect = p.getBoundingClientRect();
                offsetX = e.clientX - rect.left; offsetY = e.clientY - rect.top;
                p.style.right = 'auto'; p.style.bottom = 'auto';
                document.addEventListener('mousemove', onMouseMove);
                document.addEventListener('mouseup', onMouseUp);
                e.preventDefault();
            });
            function onMouseMove(e) {
                if (!isDragging) return;
                let x = e.clientX - offsetX; let y = e.clientY - offsetY;
                const maxX = window.innerWidth - p.offsetWidth; const maxY = window.innerHeight - p.offsetHeight;
                if (x < 0) x = 0; if (y < 0) y = 0; if (x > maxX) x = maxX; if (y > maxY) y = maxY;
                p.style.left = `${x}px`; p.style.top = `${y}px`;
            }
            function onMouseUp() {
                if (!isDragging) return;
                isDragging = false;
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                const rect = p.getBoundingClientRect();
                storage.setPanelPos(rect.left, rect.top);
            }
        }
    }

    function updateAnomalyUI(storage) {
        const anomalyEl = document.getElementById('p-anomaly');
        if (!anomalyEl) return;
        const count = storage.getAnomalyCount();
        anomalyEl.innerText = `${count} 次`;
        if (count > 0) {
            anomalyEl.classList.remove('st-val-gray');
            anomalyEl.classList.add('st-val-orange');
        } else {
            anomalyEl.classList.remove('st-val-orange');
            anomalyEl.classList.add('st-val-gray');
        }
    }

    function updateCommentTaskUI(storage) {
        const el = document.getElementById('p-comment-task');
        if (!el) return;

        if (storage.isCommentTaskDone()) {
            el.innerText = '✅ 已完成';
            el.className = 'st-value st-val-cyan';
        } else if (storage.isCommentInProgress()) {
            el.innerText = '⏳ 进行中...';
            el.className = 'st-value st-val-gold';
        } else {
            const targetTs = storage.getCommentTarget();
            if (targetTs && targetTs > Date.now()) {
                const time = new Date(targetTs).toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit'});
                el.innerText = `🔄 待触发 (${time})`;
                el.className = 'st-value st-val-gold';
            } else {
                el.innerText = '未完成';
                el.className = 'st-value st-val-gray';
            }
        }
    }

    function updateUI(statusText, timerText, durationText, statusColor, storage) {
        const s = document.getElementById('st-status');
        const t = document.getElementById('p-timer');
        const d = document.getElementById('p-duration');
        const c = document.getElementById('p-count');
        const indicator = document.getElementById('st-indicator');
        if (s) {
            s.innerText = statusText;
            let themeColor = '#00f3ff'; let shadowColor = 'rgba(0, 243, 255, 0.6)';
            if (['#00ff00','cyan','#00f3ff','#00ff99'].includes(statusColor)) { themeColor = '#00f3ff'; shadowColor = 'rgba(0, 243, 255, 0.6)'; }
            else if (['yellow','#ffcc00','#ffaa00'].includes(statusColor)) { themeColor = '#ffd700'; shadowColor = 'rgba(255, 215, 0, 0.6)'; }
            else if (['#ff6666','#ff3333','magenta'].includes(statusColor)) { themeColor = '#ff3333'; shadowColor = 'rgba(255, 51, 51, 0.6)'; }
            else if (['orange','#ff9966'].includes(statusColor)) { themeColor = '#ff9966'; shadowColor = 'rgba(255, 153, 102, 0.6)'; }
            else { themeColor = '#8899aa'; shadowColor = 'rgba(136, 153, 170, 0.3)'; }
            s.style.color = themeColor; s.style.borderColor = themeColor;
            s.style.boxShadow = `0 0 10px ${shadowColor}, inset 0 0 5px ${shadowColor}`;
            if (indicator) { indicator.style.background = themeColor; indicator.style.boxShadow = `0 0 10px ${themeColor}, 0 0 20px ${themeColor}`; }
        }
        if (t && typeof timerText === 'string') t.innerText = timerText;
        if (d && typeof durationText === 'string') d.innerText = durationText;
        if (c) c.innerText = storage.get();
        updateAnomalyUI(storage);
        updateCommentTaskUI(storage);
    }

    PX.Panel = {
        injectStyles: injectStyles,
        createPanel: createPanel,
        updateUI: updateUI,
        updateAnomalyUI: updateAnomalyUI,
        updateCommentTaskUI: updateCommentTaskUI
    };
})();
