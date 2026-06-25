# PrismaX VLA 系统完整参考

## 一、系统架构全景

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Chrome 浏览器                                │
│                                                                     │
│  ┌─ app.prismax.ai ──────────────────────────────────────────────┐  │
│  │                                                                │  │
│  │  Dashboard ──Begin Validating──▶ /data/review                  │  │
│  │                                      │                         │  │
│  │    任务列表 (Review & Earn buttons)    │                         │  │
│  │                                      ▼                         │  │
│  │  /data/review/74?upload=273  ←── 评分界面                       │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │ Episode #14460          1 of 14                          │  │  │
│  │  │                                                          │  │  │
│  │  │ ┌─────────┐ ┌─────────┐ ┌─────────┐                      │  │  │
│  │  │ │cam_left │ │cam_high │ │cam_right│   三路摄像头           │  │  │
│  │  │ └─────────┘ └─────────┘ └─────────┘                      │  │  │
│  │  │ 00:00 ═══════════════●════ 01:48  [1.0×] [🔊] [⛶]      │  │  │
│  │  │                                                          │  │  │
│  │  │ PASS/FAIL 勾选:          QUALITY 评分 (Poor→Exc):         │  │  │
│  │  │ ☐ Clear camera feed     Robot control quality  ○○○○○     │  │  │
│  │  │ ☐ Task completed        Movement smoothness   ○○○○○     │  │  │
│  │  │ ☐ Robot hand in frame   Completion speed     ○○○○○     │  │  │
│  │  │ ☐ All cameras in sync   Task fully completed ○○○○○     │  │  │
│  │  │                                                          │  │  │
│  │  │ Gate Score: [0] ═══●══════  Vote: [?]                    │  │  │
│  │  │                                                          │  │  │
│  │  │ [Submit & earn points]     (提交按钮)                      │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  ┌─ Extension Content Scripts ────────────────────────────┐   │  │
│  │  │ content-script.js → 入口，加载所有模块                     │   │  │
│  │  │ controller.js    → 页面状态检测 + HTTP Bridge 推送         │   │  │
│  │  │ panel.js         → HUD 悬浮面板 (stark-panel)              │   │  │
│  │  │ automation.js    → 主循环：排队/点击/异常检测               │   │  │
│  │  │ comment-task.js  → 评论任务                                │   │  │
│  │  │ morning.js       → 早八窗口协议                             │   │  │
│  │  │ arm-switch.js    → 机械臂切换                               │   │  │
│  │  └────────────────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ Extension Popup ───────────────────────────────────────────┐   │
│  │ 暂停脚本 | 运行统计 | 测试通知 | 更多设置                       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─ Extension Service Worker ───────────────────────────────────┐  │
│  │ 早八闹钟 (7:59) | 评论闹钟 (23:59) | Tab 管理                 │  │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
          │ HTTP POST (状态 JSON)
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Python 后端 (本机)                              │
│                                                                     │
│  Bridge_v2.py (127.0.0.1:5000)                                      │
│       ↑ 接收扩展推送的状态 JSON                                       │
│       ↓ 写入 prismax_state.json + python_heartbeat.json              │
│                                                                     │
│  state_reader_http.py → 读取状态文件                                  │
│  supervisor.py         → 进程守护，自动重启                           │
│  prismax_bot_v2.5_crossplatform.py → 主控逻辑                        │
│                                                                     │
│  ┌─ prismax_auto_judge/ (VLA 自动评分) ──────────────────────────┐  │
│  │                                                                │  │
│  │  main.py              → 入口：dry_run / assist / auto 模式      │  │
│  │  scorer.py            → 核心评分引擎                            │  │
│  │  video_features.py    → OpenCV 视频特征提取                     │  │
│  │  frame_sampler.py     → 关键帧采样                              │  │
│  │  vlm_client.py        → VLM 适配器 (v0 占位)                    │  │
│  │  schemas.py           → VLM 输出校验 (23 字段)                  │  │
│  │  config_loader.py     → YAML 配置加载                           │  │
│  │  control_adapter.py   → 浏览器操控适配器 (v0 占位)               │  │
│  │  judge_logger.py      → JSONL 日志                              │  │
│  │  processed_registry.py → 防重复提交注册表                        │  │
│  │  config.yaml          → 评分规则/阈值配置                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## 二、浏览器评分界面详细字段

### 2.1 URL 结构
```
Dashboard:     https://app.prismax.ai/
Review 列表:   https://app.prismax.ai/data/review
评分界面:      https://app.prismax.ai/data/review/{taskId}?upload={uploadId}
示例:          https://app.prismax.ai/data/review/74?upload=273
```

### 2.2 页面元素对照表

| 页面元素 | CSS Class | 类型 | scorer.py 对应 |
|---------|-----------|------|---------------|
| 任务面包屑 | `DataQAReview_breadcrumbLink__uMtJZ` | button | — |
| 场景名 | `DataQAReview_scenarioTrigger__qCwVC` | button | `episode.task_prompt` |
| 播放速度 | `DataQAReview_ctrlSpeed__G1Whv` | button | — |
| 音量 | `DataQAReview_ctrlIconBtn__DS2JH` | button | — |
| 剧场模式 | `DataQAReview_ctrlIconBtn__DS2JH` | button | — |
| **提交按钮** | `DataQAReview_submitBtn__I7VB7` | button | `should_submit` |
| 评分规则链接 | `DataQAReview_valLink__Od5GV` | a | — |

### 2.3 PASS/FAIL 勾选项（4 项）

```
☐ Clear camera feed       → 画面清晰无遮挡
☐ Task completed as instructed → 任务按指令完成
☐ Robot hand stays in frame    → 机械臂始终在画面内
☐ All cameras in sync          → 多摄像头同步
```

### 2.4 QUALITY 评分滑块（4 维度 × 5 级）

| 维度 | 等级 | scorer.py 字段 |
|------|------|---------------|
| Robot control quality | Poor / Weak / OK / Good / Exc | `scores.quality` (1-5) |
| Movement smoothness | Poor / Weak / OK / Good / Exc | `scores.smoothness` (1-5) |
| Task completion speed | Poor / Weak / OK / Good / Exc | `scores.speed` (1-5) |
| Task fully completed | Poor / Weak / OK / Good / Exc | `scores.completion` (1-5) |

### 2.5 Gate 评分

```
Score: range input [0]
Vote: [?] 投票按钮
```

### 2.6 Validator 状态

```
Innovator                         ← 验证者等级
100 / 100 spots open              ← 可用名额
0 / 30 done                       ← 已完成数 / 目标数
```

## 三、scorer.py 输出 → 浏览器表单映射

```python
# scorer.py 返回结构                          # 浏览器表单对应操作
result = {
    "decision": "PASS",          # → 全部 PASS/FAIL 勾选项打 ✓
    "should_submit": True,       # → 决定是否点击 Submit
    "confidence": 0.95,         # → (日志用)
    "risk_level": "low",        # → (日志用)
    "scores": {
        "speed": 4,              # → Completion speed: Good
        "smoothness": 5,         # → Movement smoothness: Exc
        "quality": 4,            # → Robot control quality: Good
        "diversity": 3,          # → (无直接对应)
        "completion": 5,         # → Task fully completed: Exc
    },
    "pass_probability": 0.92,   # → Gate Score 计算参考
    "reason": "...",            # → (日志用)
    "failure_modes": [],        # → 如果有，对应勾选 FAIL 项
}
```

### 3.1 评分等级映射

`schemas.py: score_100_to_slider()`:
```python
VLM 0-100 分 → 浏览器 1-5 级:
  >= 85  → 5 (Exc)
  >= 70  → 4 (Good)
  >= 50  → 3 (OK)
  >= 30  → 2 (Weak)
  < 30   → 1 (Poor)
```

### 3.2 Decision 到 PASS/FAIL 勾选

```python
if decision == "PASS":
    # 所有 PASS/FAIL 项 = True (勾选)
    "Clear camera feed"        = True
    "Task completed"           = True
    "Robot hand stays in frame" = True
    "All cameras in sync"      = True

if decision == "FAIL":
    # 根据 failure_modes 决定哪些项 False
    # 至少要有一项为 False 才能提交 FAIL

if decision == "UNCERTAIN":
    # 不提交，等待人工
```

## 四、评分表单真实 DOM 结构 (v0.2.0 实测)

### 4.1 PASS/FAIL 表格
```html
<table class="DataQAReview_gridTable__AbOV0">
  <thead>
    <tr><th></th><th>Pass</th><th>Fail</th></tr>
  </thead>
  <tbody>
    <tr> <!-- Row 0 -->
      <td class="DataQAReview_gridTdLabel__68hPC">Clear camera feed</td>
      <td class="DataQAReview_gridTdCenter__u0I-h"><span class="DataQAReview_dot__u0Ot0"></span></td>
      <td class="DataQAReview_gridTdCenter__u0I-h"><span class="DataQAReview_dot__u0Ot0"></span></td>
    </tr>
    <!-- ... 3 more rows ... -->
  </tbody>
</table>
```
- 点击 `<td>` → React 更新 `<span class="dot">` → 添加 `DataQAReview_dotSelected__` 类
- 需要触发 React 合成事件: `mousedown + mouseup + click`
- PASS col=1, FAIL col=2

### 4.2 QUALITY 表格
```html
<table class="DataQAReview_gridTable__AbOV0">  <!-- 第二个同名表格 -->
  <thead>
    <tr><th></th><th>Poor</th><th>Weak</th><th>OK</th><th>Good</th><th>Exc.</th></tr>
  </thead>
  <tbody>
    <tr> <!-- Row 0: Robot control quality -->
      <td class="gridTdLabel">Robot control quality</td>
      <td class="gridTdCenter"><span class="dot"></span></td>  <!-- Poor  col=1 -->
      <td class="gridTdCenter"><span class="dot"></span></td>  <!-- Weak  col=2 -->
      <td class="gridTdCenter"><span class="dot"></span></td>  <!-- OK    col=3 -->
      <td class="gridTdCenter"><span class="dot"></span></td>  <!-- Good  col=4 -->
      <td class="gridTdCenter"><span class="dot"></span></td>  <!-- Exc.  col=5 -->
    </tr>
    <!-- ... 3 more rows ... -->
  </tbody>
</table>
```

### 4.3 关键 CSS 选择器速查
| 用途 | 选择器 |
|------|--------|
| 表格容器 | `table.DataQAReview_gridTable__AbOV0` |
| 行 | `table.DataQAReview_gridTable__AbOV0 tbody tr` |
| 可选单元格 | `td.DataQAReview_gridTdCenter__u0I-h` |
| 单选圆点 | `.DataQAReview_dot__u0Ot0` |
| 已选圆点 | `.DataQAReview_dot__u0Ot0.DataQAReview_dotSelected__` |
| 行标签 | `.DataQAReview_rowLabelText__v2yHF` |
| 提交按钮 | `.DataQAReview_submitBtn__I7VB7` (初始 disabled) |
| PASS/FAIL 标题 | `.DataQAReview_rLabel__FE-lY` |
| Gate/Score/Vote | `.DataQAReview_statCard__IZ5rw` |

### 4.4 点击方式
```javascript
// 标准 click() 不够，React 需要合成事件序列
const dot = cell.querySelector('[class*="dot"]');
["mousedown", "mouseup", "click"].forEach(type => {
    dot.dispatchEvent(new MouseEvent(type, {bubbles: true}));
});
dot.click();
cell.click();
```

## 五、config.yaml 规则参数与界面阈值对应

```yaml
# 这些参数决定 scorer 的输出，最终驱动浏览器表单
rules:
  black_frame:     hard_fail: 0.50    # 黑帧 >50% → FAIL
  freeze_ratio:    hard_fail: 0.80    # 冻结 >80% → FAIL
  blur_score:      hard_fail: 10      # 模糊度 <10 → FAIL (画面不清晰)
  brightness:      hard_fail_min: 5   # 亮度 <5 → FAIL (黑屏)
  motion_energy:   hard_fail: 0.3     # 运动能量 <0.3 → FAIL (静止画面)

# → 如果命中 hard_fail，填表时对应 PASS/FAIL 项应标记为 Fail

decision_thresholds:
  auto_pass_min_probability: 0.86     # VLM 评分 >=86% 且 confidence >=78% → auto PASS
  auto_fail_max_probability: 0.25     # VLM 评分 <=25% → auto FAIL
  min_confidence_submit: 0.78         # 置信度门槛

safety:
  allow_auto_fail_submit: false       # false = FAIL 不自动提交
  max_auto_submit_per_run: 10         # 单次最多自动提交数
  submit_cooldown_seconds: 2          # 提交间隔
```

## 六、扩展各模块职责

### 6.1 content-script.js — 入口
- 加载顺序: Storage → Config → Notifier → Controller → Automation
- 暴露 `window.PrismAX` 调试 API
- 处理 popup ↔ content script 消息通信

### 6.2 controller.js — 状态检测
- 页面状态机: STANDBY → QUEUING → OPERATING
- 检测按钮关键词判断当前状态:
  - `["End Tele-Operation", "End Session", ...]` → OPERATING
  - `["Leave", "Leave Queue", ...]` → QUEUING
  - `["Begin Validating", "Enter Live Control", ...]` → STANDBY
- HTTP Bridge: POST 状态到 `http://127.0.0.1:5000`
- 推送间隔: 500ms (normal) / 3000ms (standby)
- 钱包弹窗检测 + 自动关闭

### 6.3 panel.js — HUD 面板
- 注入 `#stark-panel` 到页面右下角
- 显示: 自动刷新倒数、排队时长、异常次数、评论任务、今日战绩
- 按钮: 暂停脚本 / 重置协议
- 可拖拽、可折叠
- 仅在 controller 检测到有效页面状态后注入

### 6.4 automation.js — 主循环
- 队列监控 + 自动点击进入
- 异常检测: 操作时长 <40s → 异常
- 连续异常 ≥2 → 自动退出 + 冷却 60 分钟
- 跨天自动刷新
- 早八窗口 (08:01-08:06) 特殊处理
- 排名检测 + 静候模式 (rank >100 → 降频)

### 6.5 popup.js — 弹窗
- 4 按钮: 暂停脚本 | 运行统计 | 测试通知 | 更多设置
- 每 2 秒自动刷新状态
- 通过 `chrome.tabs.sendMessage` 与 content script 通信

### 6.6 service-worker.js — 后台
- 早八闹钟: 每天 7:59
- 评论闹钟: 每天 23:59
- Tab 管理: 自动查找/创建 PrismaX 标签页

## 七、control_adapter.py 待实现接口

```python
class PrismaXControlAdapter:
    """
    当前 v0 所有方法抛出 NotImplementedError。
    需要实现以下浏览器操控逻辑：
    """

    def open_page(self) -> None:
        """打开 PrismaX 页面并登录"""
        # Playwright CDP: 连接到已有 Chrome
        # 或启动新浏览器 + 加载扩展

    def get_current_episode(self) -> dict:
        """获取当前评分页面的 episode 信息"""
        # 解析页面 DOM:
        # - Episode #14460 (正则: /Episode #(\d+)/)
        # - 任务名 (DataQAReview_scenarioTrigger)
        # - 视频 URL (video 元素 src)
        # - 摄像头视图列表 (cam_left, cam_high, cam_right)

    def fill_result(self, result: dict) -> None:
        """将 scorer 结果填入表单"""
        # PASS/FAIL 勾选: 寻找对应的 checkbox/radio
        # Quality 滑块: input[type=range] 设置 value
        # Gate Score: range input
        # 需要先分析页面 DOM 确定具体 selector

    def submit(self) -> None:
        """点击 Submit & earn points"""
        # 定位: button.DataQAReview_submitBtn__I7VB7
        # 或: button:has-text('Submit & earn points')

    def next_episode(self) -> None:
        """导航到下一个 episode"""
        # 点击 "Next" 箭头或 episode 编号

    def skip_episode(self, reason: str) -> None:
        """跳过当前 episode"""
        # 记录跳过原因到日志
```

## 八、DOM 选择器速查表

| 目标 | 选择器 |
|------|--------|
| Begin Validating 按钮 | `button:has-text('Begin Validating')` |
| Review & Earn 按钮 | `button:has-text('Review & Earn')` |
| Submit 按钮 | `.DataQAReview_submitBtn__I7VB7` |
| 场景/任务名 | `.DataQAReview_scenarioTrigger__qCwVC` |
| 面包屑 | `.DataQAReview_breadcrumbLink__uMtJZ` |
| 评分面板 | `.DataQAReview_panel__0xNzL` |
| PASS/FAIL 表格 | `table.DataQAReview_gridTable__AbOV0` (第一个) |
| QUALITY 表格 | `table.DataQAReview_gridTable__AbOV0` (第二个) |
| 表格行 | `table.DataQAReview_gridTable__AbOV0 tbody tr` |
| 点击单元格 | `td.DataQAReview_gridTdCenter__u0I-h` |
| 单选圆点 | `.DataQAReview_dot__u0Ot0` |
| 已选圆点 | `.DataQAReview_dot__u0Ot0.DataQAReview_dotSelected__` |
| 行标签 | `.DataQAReview_rowLabelText__v2yHF` |
| 播放速度 | `.DataQAReview_ctrlSpeed__G1Whv` |
| Episode 标题 | 页面文本正则: `Episode #(\d+)` |
| 进度 (1 of 14) | 页面文本正则: `(\d+) of (\d+)` |
| 视频元素 | `video` |
| 扩展面板 | `#stark-panel` |

## 九、数据流完整路径

```
1. 视频输入
   prismax_auto_judge/data/videos/{episode_id}_main.mp4
   prismax_auto_judge/data/videos/{episode_id}_left_wrist.mp4
   prismax_auto_judge/data/videos/{episode_id}_right_wrist.mp4

2. Python 评分 (main.py → scorer.py)
   视频 → video_features.py (CV特征)
        → frame_sampler.py (关键帧)
        → scorer._evaluate_rules() (规则引擎)
        → vlm_client.py (VLM, 可选)
        → scorer._decide_from_vlm() (决策)
        → 输出 result dict

3. 本地日志
   prismax_auto_judge/data/logs/scoring_log.jsonl     (JSONL 日志)
   prismax_auto_judge/data/logs/processed_episodes.json (防重复)

4. 浏览器填表 (control_adapter.py, 待实现)
   result.decision → 勾选 PASS/FAIL
   result.scores   → Quality 滑块
   result.should_submit → 点击 Submit

5. 扩展状态推送
   controller.js → HTTP POST → Bridge_v2.py (127.0.0.1:5000)
   → prismax_state.json → state_reader_http.py
   → supervisor.py (进程守护)

6. 通知
   扩展 → PushDeer / 企业微信 / Server酱 / Telegram
```

## 十、运行模式对照

| 模式 | config.yaml | 行为 |
|------|-------------|------|
| `dry_run` | `runtime.mode: "dry_run"` | 本地分析视频，日志记录，**不操作浏览器** |
| `assist_preview` | — | 分析 + 预览，**不提交** |
| `assist_fill` | — | 分析 + **填表但不提交** |
| `auto` | — | 分析 + 填表 + **自动提交** (多重安全守卫) |
