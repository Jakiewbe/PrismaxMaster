import pydirectinput
import pyautogui
import time
import random
import threading
import tkinter as tk
import os
import json
import keyboard
import gc
import ctypes
from ctypes import wintypes
from config_shared import PYTHON_HEARTBEAT_FILE

# ========== 🔒 窗口焦点检测（防止OKX钱包弹窗抢焦点） ==========
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

def _get_foreground_window_title():
    """获取当前前台窗口标题"""
    hwnd = _user32.GetForegroundWindow()
    if hwnd == 0:
        return ""
    length = _user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def _find_prismax_window():
    """枚举所有窗口，找到 PrismaX 浏览器窗口句柄"""
    found = []

    def enum_callback(hwnd, _):
        length = _user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        if "PrismaX" in buf.value:
            found.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    _user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    return found[0] if found else None

def _try_refocus_prismax():
    """尝试将 PrismaX 浏览器窗口恢复到前台"""
    hwnd = _find_prismax_window()
    if not hwnd:
        return False

    # 如果窗口最小化了，先恢复
    SW_RESTORE = 9
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, SW_RESTORE)

    # 尝试设为前台窗口
    _user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)
    return "PrismaX" in _get_foreground_window_title()

def is_prismax_focused():
    """检查 PrismaX 浏览器窗口是否在前台（防止OKX钱包弹窗抢焦点）"""
    title = _get_foreground_window_title()
    if not title:
        return False
    return "PrismaX" in title

# 连续失焦计数（防止瞬时切换导致误判）
_focus_lost_count = 0
FOCUS_LOST_THRESHOLD = 3  # 连续3次检测失焦才确认

def check_focus():
    """检查窗口焦点，返回 (是否聚焦, 当前窗口标题)"""
    global _focus_lost_count
    title = _get_foreground_window_title()
    focused = "PrismaX" in title if title else False
    if not focused:
        _focus_lost_count += 1
    else:
        _focus_lost_count = 0
    confirmed_lost = _focus_lost_count >= FOCUS_LOST_THRESHOLD
    return (not confirmed_lost), title

def recover_focus():
    """
    🔒 焦点恢复：当检测到失焦（OKX钱包弹窗）时，尝试抢回焦点
    返回 True 表示恢复成功
    """
    global _focus_lost_count

    print("[焦点恢复] 🔧 开始恢复流程...")
    fg_title = _get_foreground_window_title()
    print(f"[焦点恢复] 当前前台窗口: {fg_title}")

    for attempt in range(5):
        # 策略1: 发送 Escape 关闭弹窗（pydirectinput 全局发送，弹窗会收到）
        print(f"[焦点恢复] 尝试 {attempt+1}/5: 发送 Escape...")
        try:
            pydirectinput.press('escape')
        except:
            pass
        time.sleep(0.3)

        # 检查弹窗是否已关闭
        new_title = _get_foreground_window_title()
        if "PrismaX" in new_title:
            _focus_lost_count = 0
            print(f"[焦点恢复] ✅ 第{attempt+1}次尝试成功恢复焦点")
            return True

        print(f"[焦点恢复] 当前窗口仍为: {new_title}")

        # 策略2: 尝试把 PrismaX 窗口拉到前台
        if _try_refocus_prismax():
            _focus_lost_count = 0
            print(f"[焦点恢复] ✅ 通过SetForegroundWindow恢复焦点")
            return True

        # 策略3: Alt+Tab 切换窗口（最后的办法）
        if attempt >= 2:
            print(f"[焦点恢复] 尝试 Alt+Tab 切换...")
            try:
                pydirectinput.keyDown('alt')
                time.sleep(0.05)
                pydirectinput.press('tab')
                time.sleep(0.05)
                pydirectinput.keyUp('alt')
                time.sleep(0.3)

                if "PrismaX" in _get_foreground_window_title():
                    _focus_lost_count = 0
                    print(f"[焦点恢复] ✅ 通过Alt+Tab恢复焦点")
                    return True
            except:
                pass

        time.sleep(0.5)

    print(f"[焦点恢复] ❌ 5次尝试失败，等待下次循环重试")
    return False

# ========== ✨ 新增：导入状态读取器 ==========
try:
    from state_reader_http import StateReader
    STATE_READER_AVAILABLE = True
    print("[状态读取器] ✅ 已加载 (HTTP 版本)")
except ImportError:
    STATE_READER_AVAILABLE = False
    print("[状态读取器] ⚠️ 未找到 state_reader_http.py")
    print("[状态读取器] ⚠️ 请确保文件在同一目录，并运行 Bridge_v2.py")
# ==========================================

# ================= 🔧 核心配置 =================
CONFIG_FILE = 'prismax_config.json'

# 操作参数
MOVE_DURATION_MIN = 1.5
MOVE_DURATION_MAX = 4.0
COMBO_CHANCE = 0.65
MICRO_ADJUST_CHANCE = 0.25

# 🎯 智能休息时间
REST_TIMES = {
    'urgent': (0.15, 0.35),
    'active': (0.25, 0.50),
    'normal': (0.40, 0.80),
    'init': (0.50, 1.20)
}

REST_MIN = 0.3
REST_MAX = 0.8

# ================= 🎮 键位映射 =================
AXES = {
    'base': {'cw': 'a', 'ccw': 'd', 'weight': 15},
    'elbow': {'up': 'up', 'down': 'down', 'weight': 12},
    'hand_rotate': {'cw': 'z', 'ccw': 'x', 'weight': 8},
    'grip': {'open': 'c', 'close': 'v', 'weight': 15},
    'z_axis': {'up': 'q', 'down': 'e', 'weight': 10},
    'y_axis': {'forward': 'w', 'backward': 's', 'weight': 15},
    'lateral': {'left': 'left', 'right': 'right', 'weight': 5}
}

CONFLICTS = {
    'w': 's', 's': 'w', 'a': 'd', 'd': 'a',
    'c': 'v', 'v': 'c', 'up': 'down', 'down': 'up',
    'left': 'right', 'right': 'left', 'q': 'e', 'e': 'q',
    'z': 'x', 'x': 'z'
}

COMBO_RULES = {
    'y_axis': ['base', 'grip', 'z_axis'],
    'base': ['y_axis', 'elbow', 'grip'],
    'elbow': ['base', 'hand_rotate', 'y_axis'],
    'grip': ['y_axis', 'base', 'z_axis'],
    'z_axis': ['y_axis', 'grip'],
    'hand_rotate': ['elbow', 'y_axis']
}

weighted_keys = []
for axis, config in AXES.items():
    weight = config['weight']
    for direction, key in config.items():
        if direction != 'weight':
            weighted_keys.extend([key] * weight)

all_keys = set()
for axis, config in AXES.items():
    for direction, key in config.items():
        if direction != 'weight':
            all_keys.add(key)
all_keys = sorted(all_keys)

# ================= 🎨 全局状态 =================
pydirectinput.PAUSE = 0.01
pydirectinput.FAILSAFE = False

app_state = {
    "status": "系统启动中...",
    "mode": "⏸ 待机",
    "active_keys": "--",
    "total_actions": 0,
    "session_time": "00:00",
    "js_state": "⚪ 未连接",        # ✨ 新增：JS端状态
    "allow_operation": False,       # ✨ 新增：操作授权
    "js_operations": 0,             # ✨ 新增：JS端操作次数
    "js_anomaly": 0,                # ✨ 新增：JS端异常次数
    "phase": "待机",
    "error_count": 0,
    "last_error": "",
    "focus_lost": False,            # 🔒 窗口焦点丢失警告
    "focus_title": "",             # 🔒 当前前台窗口标题
    "wallet_popup": False          # 🔒 钱包弹窗检测
}

bot_paused = False
bot_running = True
last_allow_at = 0
last_heartbeat_write = 0
last_axis = None
axis_usage = {axis: 0 for axis in AXES.keys()}

action_should_stop = threading.Event()
heartbeat_lock = threading.Lock()

def write_python_heartbeat(last_error=None, running=None):
    """写入主控心跳，供 Bridge/supervisor 判断 Python 驻守是否正常。"""
    global last_allow_at, last_heartbeat_write
    now = time.time()
    if last_error is None and running is None and now - last_heartbeat_write < 1:
        return
    last_heartbeat_write = now
    payload = {
        "pid": os.getpid(),
        "running": bot_running if running is None else running,
        "paused": bot_paused,
        "lastHeartbeatAt": int(now * 1000),
        "lastAllowAt": int(last_allow_at * 1000) if last_allow_at else 0,
        "lastError": (last_error if last_error is not None else app_state.get("last_error", "")) or "",
        "mode": app_state.get("mode", ""),
        "status": app_state.get("status", ""),
    }
    tmp_path = f"{PYTHON_HEARTBEAT_FILE}.tmp"
    try:
        with heartbeat_lock:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, PYTHON_HEARTBEAT_FILE)
    except Exception as e:
        print(f"[心跳写入错误] {e}")

# ================= 🛠️ 工具函数 =================
def update_key_display(keys_list):
    if not keys_list:
        app_state["active_keys"] = "--"
    else:
        display = []
        for k in keys_list:
            if k == 'up': display.append('↑')
            elif k == 'down': display.append('↓')
            elif k == 'left': display.append('←')
            elif k == 'right': display.append('→')
            else: display.append(k.upper())
        app_state["active_keys"] = " + ".join(display)

def safe_key_down(key):
    try:
        pydirectinput.keyDown(key)
    except Exception as e:
        print(f"[KeyDown错误] {key}: {e}")

def safe_key_up(key):
    try:
        pydirectinput.keyUp(key)
    except Exception as e:
        print(f"[KeyUp错误] {key}: {e}")

def safe_key_up_all():
    for k in all_keys:
        try:
            pydirectinput.keyUp(k)
        except:
            pass
    update_key_display([])

# ================= 🎯 智能选键 =================
def select_smart_move():
    global last_axis, axis_usage
    
    candidates = [ax for ax in AXES.keys() if ax != last_axis]
    weights = []
    for ax in candidates:
        usage = axis_usage[ax]
        avg = sum(axis_usage.values()) / len(axis_usage)
        weight = max(1, AXES[ax]['weight'] - (usage - avg))
        weights.append(weight)
    
    main_axis = random.choices(candidates, weights=weights)[0]
    
    axis_config = AXES[main_axis]
    directions = [k for k in axis_config.keys() if k != 'weight']
    direction = random.choice(directions)
    main_key = axis_config[direction]
    
    combo_key = None
    combo_axis = None
    
    if random.random() < COMBO_CHANCE and main_axis in COMBO_RULES:
        combo_candidates = COMBO_RULES[main_axis]
        if combo_candidates:
            combo_axis = random.choice(combo_candidates)
            combo_config = AXES[combo_axis]
            combo_dirs = [k for k in combo_config.keys() if k != 'weight']
            combo_dir = random.choice(combo_dirs)
            combo_key = combo_config[combo_dir]
            
            if combo_key == CONFLICTS.get(main_key):
                combo_key = None
                combo_axis = None
    
    last_axis = main_axis
    axis_usage[main_axis] += 1
    if combo_axis:
        axis_usage[combo_axis] += 1
    
    return main_key, combo_key, main_axis, combo_axis

# ================= 🤖 可中断的操作执行（新架构） =================
def execute_move_interruptible(phase='normal', is_first=False, reader=None):
    """执行操作（新架构：持续检测 JS 授权）"""
    
    if is_first:
        app_state["status"] = "⚡ 初始化探索"
        update_key_display(['W'])
        safe_key_down('w')

        start = time.time()
        while time.time() - start < 1.5:
            if action_should_stop.is_set():
                break
            focused, fg_title = check_focus()
            if not focused:
                print(f"[⚠ 焦点丢失] 当前窗口: {fg_title} | 立即释放所有按键")
                app_state["focus_lost"] = True
                app_state["focus_title"] = fg_title
                safe_key_up_all()
                action_should_stop.set()
                break
            app_state["focus_lost"] = False
            app_state["focus_title"] = ""
            time.sleep(0.1)

        safe_key_up('w')
        update_key_display([])
        time.sleep(0.3)

        update_key_display(['A', 'C'])
        safe_key_down('a')
        time.sleep(0.2)
        safe_key_down('c')

        start = time.time()
        while time.time() - start < 1.0:
            if action_should_stop.is_set():
                break
            focused, fg_title = check_focus()
            if not focused:
                print(f"[⚠ 焦点丢失] 当前窗口: {fg_title} | 立即释放所有按键")
                app_state["focus_lost"] = True
                app_state["focus_title"] = fg_title
                safe_key_up_all()
                action_should_stop.set()
                break
            app_state["focus_lost"] = False
            app_state["focus_title"] = ""
            time.sleep(0.1)

        safe_key_up('c')
        safe_key_up('a')
        update_key_display([])
        return
    
    if phase == 'urgent':
        duration_min, duration_max = 1.0, 2.5
        micro_chance = 0.1
    elif phase == 'active':
        duration_min, duration_max = 1.5, 3.5
        micro_chance = 0.2
    else:
        duration_min, duration_max = MOVE_DURATION_MIN, MOVE_DURATION_MAX
        micro_chance = MICRO_ADJUST_CHANCE
    
    use_micro = random.random() < micro_chance
    
    if use_micro:
        execute_micro_adjust_interruptible(duration_min, duration_max, reader)
    else:
        execute_normal_move_interruptible(duration_min, duration_max, phase, reader)

def execute_normal_move_interruptible(duration_min, duration_max, phase, reader):
    """正常移动（新架构：带 JS 授权检测）"""
    main_key, combo_key, main_axis, combo_axis = select_smart_move()
    duration = random.uniform(duration_min, duration_max)
    
    active_keys = [main_key]
    if combo_key:
        active_keys.append(combo_key)
    
    update_key_display(active_keys)
    
    axis_names = {
        'base': '基座', 'elbow': '肘部', 'hand_rotate': '手腕',
        'grip': '夹爪', 'z_axis': 'Z轴', 'y_axis': 'Y轴', 'lateral': '横移'
    }
    
    main_name = axis_names.get(main_axis, main_axis)
    if combo_key and combo_axis:
        combo_name = axis_names.get(combo_axis, combo_axis)
        app_state["status"] = f"🔄 {main_name}+{combo_name} ({duration:.1f}s)"
    else:
        app_state["status"] = f"➡️ {main_name} ({duration:.1f}s)"
    
    safe_key_down(main_key)
    if combo_key:
        time.sleep(random.uniform(0.08, 0.2))
        safe_key_down(combo_key)
    
    start_time = time.time()
    
    while time.time() - start_time < duration:
        if action_should_stop.is_set():
            break

        # 🔒 焦点检测：防止OKX钱包弹窗抢焦点导致按键泄漏到密码框
        focused, fg_title = check_focus()
        if not focused:
            print(f"[⚠ 焦点丢失] 当前窗口: {fg_title} | 立即释放所有按键")
            app_state["focus_lost"] = True
            app_state["focus_title"] = fg_title
            safe_key_up_all()
            action_should_stop.set()
            break
        app_state["focus_lost"] = False
        app_state["focus_title"] = ""

        time.sleep(0.1)

    if combo_key:
        safe_key_up(combo_key)
        time.sleep(random.uniform(0.05, 0.15))
    safe_key_up(main_key)
    
    update_key_display([])

def execute_micro_adjust_interruptible(duration_min, duration_max, reader):
    """微调模式（新架构：带 JS 授权检测）"""
    main_key, combo_key, main_axis, combo_axis = select_smart_move()
    
    taps = random.randint(2, 4)
    tap_duration = random.uniform(duration_min, duration_max) / taps
    
    app_state["status"] = f"🎯 精细微调 (x{taps})"
    
    active_keys = [main_key]
    if combo_key:
        active_keys.append(combo_key)
    
    for i in range(taps):
        if action_should_stop.is_set():
            break
        
        # ⚠️ BUG修复：移除重复授权检查（同上）
        
        update_key_display(active_keys)
        
        safe_key_down(main_key)
        if combo_key:
            time.sleep(0.05)
            safe_key_down(combo_key)
        
        start = time.time()
        actual_duration = tap_duration * random.uniform(0.6, 0.9)
        while time.time() - start < actual_duration:
            if action_should_stop.is_set():
                break
            # 🔒 焦点检测：防止OKX钱包弹窗抢焦点
            focused, fg_title = check_focus()
            if not focused:
                print(f"[⚠ 焦点丢失] 当前窗口: {fg_title} | 立即释放所有按键")
                app_state["focus_lost"] = True
                app_state["focus_title"] = fg_title
                safe_key_up_all()
                action_should_stop.set()
                break
            app_state["focus_lost"] = False
            app_state["focus_title"] = ""
            time.sleep(0.05)
        
        if combo_key:
            safe_key_up(combo_key)
        safe_key_up(main_key)
        
        update_key_display([])
        
        if i < taps - 1:
            time.sleep(random.uniform(0.1, 0.3))

# ================= 🖥️ 优化版 HUD（新架构） =================
THEME = {
    'bg': '#050a14',
    'border': '#00e5ff',
    'text_main': '#00e5ff',
    'text_gold': '#ffd700',
    'btn_bg': '#112233',
    'btn_hover': '#1a3a5c',
    'status_green': '#00ff66',
    'status_red': '#ff3333',
    'status_gray': '#666666',
    'status_yellow': '#ffcc00'
}

class SmartHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg=THEME['bg'])

        scr_w, scr_h = pyautogui.size()
        self.root.geometry(f"400x320+{scr_w - 420}+{scr_h - 360}")  # 高度从 260 增加到 320

        # 边框
        border = tk.Frame(self.root, bg=THEME['border'], padx=2, pady=2)
        border.pack(fill='both', expand=True)
        main = tk.Frame(border, bg=THEME['bg'])
        main.pack(fill='both', expand=True)

        # 标题栏
        header = tk.Frame(main, bg=THEME['bg'])
        header.pack(fill='x', padx=10, pady=8)

        self.indicator = tk.Label(
            header, text="●", font=("Arial", 16),
            fg='#888', bg=THEME['bg']
        )
        self.indicator.pack(side='left')

        tk.Label(
            header, text="PRISMAX AI v2.5",
            font=("Impact", 14),
            fg=THEME['text_gold'], bg=THEME['bg']
        ).pack(side='left', padx=5)

        self.lbl_mode = tk.Label(
            header, text="待机",
            font=("微软雅黑", 10, "bold"),
            fg=THEME['text_main'], bg=THEME['bg']
        )
        self.lbl_mode.pack(side='right')

        # 信息区
        info = tk.Frame(main, bg=THEME['bg'])
        info.pack(fill='x', padx=10, pady=5)

        # 左侧统计
        stats = tk.Frame(info, bg=THEME['bg'])
        stats.pack(side='left', anchor='w')

        self.lbl_session = tk.Label(
            stats, text="会话: 00:00",
            font=("Consolas", 10),
            fg="#fff", bg=THEME['bg']
        )
        self.lbl_session.pack(anchor='w')

        self.lbl_actions = tk.Label(
            stats, text="操作次数: 0",
            font=("Arial", 9),
            fg="#888", bg=THEME['bg']
        )
        self.lbl_actions.pack(anchor='w')
        
        # ✨ 新增：JS 端状态显示（紧凑版）
        js_frame = tk.Frame(stats, bg=THEME['bg'])
        js_frame.pack(anchor='w', pady=3)
        
        self.lbl_js_status = tk.Label(
            js_frame, text="JS:●",
            font=("Arial", 8, "bold"),
            fg=THEME['status_gray'], bg=THEME['bg']
        )
        self.lbl_js_status.pack(side='left', padx=(0, 10))
        
        self.lbl_allow_status = tk.Label(
            js_frame, text="授权:❌",
            font=("Arial", 8, "bold"),
            fg=THEME['status_red'], bg=THEME['bg']
        )
        self.lbl_allow_status.pack(side='left')
        
        # JS 端统计信息
        self.lbl_js_stats = tk.Label(
            stats, text="",
            font=("Arial", 7),
            fg="#888", bg=THEME['bg']
        )
        self.lbl_js_stats.pack(anchor='w')
        
        # 错误信息
        self.lbl_error = tk.Label(
            stats, text="",
            font=("Arial", 7),
            fg="#ff6666", bg=THEME['bg']
        )
        self.lbl_error.pack(anchor='w')

        # 右侧按键
        self.lbl_keys = tk.Label(
            info, text="--",
            font=("Arial", 22, "bold"),
            fg=THEME['text_gold'], bg=THEME['bg']
        )
        self.lbl_keys.pack(side='right')

        # 状态
        self.lbl_status = tk.Label(
            main, text="初始化...",
            font=("微软雅黑", 9),
            fg="#aaa", bg=THEME['bg']
        )
        self.lbl_status.pack(pady=5)

        # 按钮
        btn_frame = tk.Frame(main, bg=THEME['bg'])
        btn_frame.pack(side='bottom', fill='x', pady=5, padx=5)

        self.create_btn("启动/暂停 [F9]", self.toggle_pause, btn_frame)
        self.create_btn("退出 [ESC]", self.quit_app, btn_frame)

        # 拖拽
        self.root.bind("<Button-1>", lambda e: setattr(self, '_x', e.x) or setattr(self, '_y', e.y))
        self.root.bind("<B1-Motion>", lambda e: self.root.geometry(
            f"+{self.root.winfo_x() + (e.x - self._x)}+{self.root.winfo_y() + (e.y - self._y)}"
        ))

        # 呼吸灯计数器
        self.blink_counter = 0
        
        # 🆕 性能优化：状态缓存（避免重复更新）
        self._last_state = {}
        self._update_interval = 100  # 基础更新间隔(ms)，从50提升到100
        self._blink_interval = 50    # 呼吸灯间隔(ms)，保持快速

        self._update_loop()
        self._blink_loop()  # 🆕 独立的呼吸灯循环
        self.root.mainloop()

    def create_btn(self, text, cmd, parent):
        btn = tk.Button(
            parent, text=text, command=cmd,
            font=("微软雅黑", 8),
            bg=THEME['btn_bg'], fg='white',
            activebackground=THEME['btn_hover'],
            bd=0, padx=5, pady=2
        )
        btn.pack(side='left', expand=True, fill='x', padx=2)

    def toggle_pause(self):
        global bot_paused
        bot_paused = not bot_paused

    def quit_app(self):
        global bot_running
        bot_running = False
        safe_key_up_all()
        write_python_heartbeat(running=False)
        try:
            self.root.destroy()
        except:
            pass

    def _has_changed(self, key, value):
        """🆕 检查状态是否变化"""
        if self._last_state.get(key) != value:
            self._last_state[key] = value
            return True
        return False
    
    def _update_loop(self):
        """🆕 优化版更新循环：只在状态变化时更新 UI"""
        
        # 基础信息更新（仅在变化时）
        if self._has_changed('status', app_state["status"]):
            self.lbl_status.config(text=app_state["status"])
        
        if self._has_changed('mode', app_state["mode"]):
            self.lbl_mode.config(text=app_state["mode"])
            # 同时更新主指示器颜色
            mode = app_state["mode"]
            if "运行" in mode:
                color = "#00ff00"
            elif "待机" in mode:
                color = THEME['text_main']
            elif "暂停" in mode:
                color = "#ff3333"
            else:
                color = "#888"
            self.indicator.config(fg=color)
        
        if self._has_changed('active_keys', app_state["active_keys"]):
            self.lbl_keys.config(text=app_state["active_keys"])
        
        if self._has_changed('session_time', app_state['session_time']):
            self.lbl_session.config(text=f"会话: {app_state['session_time']}")
        
        if self._has_changed('total_actions', app_state['total_actions']):
            self.lbl_actions.config(text=f"操作次数: {app_state['total_actions']}")

        # JS 端状态显示（仅在变化时）
        js_state = app_state["js_state"]
        if self._has_changed('js_state', js_state):
            if "🟢" in js_state or "操作中" in js_state:
                self.lbl_js_status.config(text="JS:●", fg=THEME['status_green'])
            elif "🟡" in js_state or "排队中" in js_state:
                self.lbl_js_status.config(text="JS:●", fg=THEME['status_yellow'])
            elif "🔵" in js_state or "待机" in js_state:
                self.lbl_js_status.config(text="JS:●", fg=THEME['status_gray'])
            elif "🔴" in js_state or "未连接" in js_state or "失败" in js_state:
                self.lbl_js_status.config(text="JS:●", fg=THEME['status_red'])
            else:
                self.lbl_js_status.config(text="JS:●", fg=THEME['status_gray'])
        
        # JS 端统计信息（仅在变化时）
        js_ops = app_state.get("js_operations", 0)
        js_ano = app_state.get("js_anomaly", 0)
        js_stats_key = f"{js_ops}_{js_ano}"
        if self._has_changed('js_stats', js_stats_key):
            if js_ops > 0 or js_ano > 0:
                self.lbl_js_stats.config(text=f"JS统计: 成功{js_ops} 异常{js_ano}")
            else:
                self.lbl_js_stats.config(text="")
        
        # 错误信息（仅在变化时）
        error_count = app_state["error_count"]
        focus_lost = app_state.get("focus_lost", False)
        wallet_popup = app_state.get("wallet_popup", False)
        error_display_key = f"{error_count}_{focus_lost}_{wallet_popup}"
        if self._has_changed('error_display', error_display_key):
            if wallet_popup:
                self.lbl_error.config(text=f"⚠ 钱包弹窗! 已暂停按键", fg="#ffcc00")
            elif focus_lost:
                fg_title = app_state.get("focus_title", "")
                self.lbl_error.config(text=f"🔴 焦点丢失! {fg_title[:25]}", fg="#ff3333")
            elif error_count > 0:
                self.lbl_error.config(text=f"⚠ 错误x{error_count}", fg="#ff6666")
            else:
                self.lbl_error.config(text="")

        self.root.after(self._update_interval, self._update_loop)
    
    def _blink_loop(self):
        """🆕 独立的呼吸灯循环（保持快速响应）"""
        allow_operation = app_state["allow_operation"]
        
        if allow_operation:
            self.blink_counter += 1
            if self.blink_counter % 6 < 3:
                self.lbl_allow_status.config(text="授权:✅", fg=THEME['status_green'])
            else:
                self.lbl_allow_status.config(text="授权:✅", fg="#003300")
        else:
            # 只在状态变化时更新（避免重复设置）
            if self._has_changed('allow_operation', allow_operation):
                self.lbl_allow_status.config(text="授权:❌", fg=THEME['status_red'])
        
        self.root.after(self._blink_interval, self._blink_loop)

# ================= 🤖 主逻辑（新架构：JS 主导） =================
def bot_logic():
    """主逻辑循环（新架构：JS 端权威，Python 端执行）"""
    global bot_paused, last_allow_at

    print("=" * 60)
    print("[系统] 启动序列开始...")
    print("=" * 60)

    # ========== 初始化状态读取器 ==========
    if not STATE_READER_AVAILABLE:
        print("[系统] ❌ 状态读取器不可用")
        print("[系统] ⚠️ 请确保:")
        print("  1. state_reader_http.py 在同目录")
        print("  2. 已安装 requests: pip install requests")
        print("  3. 已安装 pygetwindow: pip install pygetwindow")
        print("=" * 60)
        app_state["status"] = "⚠️ 未检测到状态读取器"
        app_state["js_state"] = "🔴 模块缺失"
        time.sleep(10)
        return

    try:
        reader = StateReader()
        print("[系统] ✅ 状态读取器已初始化")
        print("[系统] 📡 等待 JS 端状态信号...")
        print("=" * 60)
    except Exception as e:
        print(f"[系统] ❌ 状态读取器初始化失败: {e}")
        app_state["status"] = f"⚠️ 初始化失败: {e}"
        app_state["js_state"] = "🔴 初始化错误"
        time.sleep(10)
        return

    # ========== 主循环变量 ==========
    session_start = None
    is_first_action = True
    consecutive_errors = 0
    max_consecutive_errors = 5
    last_allow_state = False

    print("[系统] 🚀 主逻辑启动（新架构）")
    print("[系统] 💡 JS 端检测 → Python 端执行")
    print("=" * 60)

    while bot_running:
        try:
            write_python_heartbeat()
            # ========== 快捷键处理 ==========
            try:
                if keyboard.is_pressed('esc'):
                    safe_key_up_all()
                    action_should_stop.set()
                    bot_paused = True
                    time.sleep(0.5)

                if keyboard.is_pressed('f9'):
                    bot_paused = not bot_paused
                    if bot_paused:
                        action_should_stop.set()
                        safe_key_up_all()
                        print("[系统] ⏸ 已暂停")
                    else:
                        is_first_action = True
                        print("[系统] ▶ 已恢复")
                    time.sleep(0.3)
            except Exception as e:
                print(f"[快捷键错误] {e}")

            # ========== 暂停状态 ==========
            if bot_paused:
                app_state["mode"] = "⏸ 暂停"
                app_state["status"] = "等待指令..."
                app_state["phase"] = "待机"
                time.sleep(0.1)
                continue

            # ========== 会话时间更新 ==========
            if session_start:
                elapsed = int(time.time() - session_start)
                mins, secs = divmod(elapsed, 60)
                app_state["session_time"] = f"{mins:02d}:{secs:02d}"
            else:
                app_state["session_time"] = "00:00"

            # ========== ✨ 核心改动：读取 JS 端状态 ==========
            try:
                state_info = reader.get_state_info()

                # 更新 UI 显示
                app_state["js_state"] = state_info['status']
                app_state["allow_operation"] = state_info['allow_operation']

                # 同步 JS 端统计（仅用于显示）
                app_state["js_operations"] = state_info.get('total_operations', 0)
                app_state["js_anomaly"] = state_info.get('anomaly_count', 0)

                # 🔒 钱包弹窗状态
                wallet_active = state_info.get('wallet_popup_active', False)
                app_state["wallet_popup"] = wallet_active

                # ✅ 修复：不从 JS 端覆盖操作计数
                # Python 端自己维护 total_actions
                
            except Exception as e:
                print(f"[状态读取错误] {e}")
                app_state["js_state"] = "🔴 读取失败"
                app_state["allow_operation"] = False
                consecutive_errors += 1
                time.sleep(1)
                continue
            
            # ========== ✅ 核心判断：是否允许操作 ==========
            allow_operation = reader.is_allowed_to_operate()

            # 🔒 双重保险：钱包弹窗活跃时强制禁止操作
            if app_state.get("wallet_popup", False):
                allow_operation = False
                app_state["status"] = "⚠ 钱包弹窗拦截"
            
            if allow_operation:
                # 🔒 窗口焦点检测：防止OKX钱包弹窗抢焦点
                focused, fg_title = check_focus()
                if not focused:
                    print(f"[⚠ 焦点丢失] 当前窗口: {fg_title} | 尝试恢复...")
                    app_state["focus_lost"] = True
                    app_state["focus_title"] = fg_title
                    app_state["mode"] = "🔴 焦点丢失"
                    app_state["status"] = f"⚠ 窗口失焦，正在恢复..."
                    safe_key_up_all()
                    action_should_stop.set()

                    # 🔧 主动恢复焦点（Escape → SetForegroundWindow → Alt+Tab）
                    recover_focus()

                    if is_prismax_focused():
                        app_state["focus_lost"] = False
                        app_state["focus_title"] = ""
                        app_state["status"] = "✅ 焦点已恢复"
                        print("[系统] ✅ 焦点已恢复，继续操作")
                        time.sleep(0.5)
                    else:
                        app_state["status"] = "⚠ 焦点恢复失败，等待中..."
                        print("[系统] ⚠ 焦点恢复失败，等待下次尝试")
                        time.sleep(2.0)
                    continue

                last_allow_at = time.time()
                # ✅ JS 端授权，开始操作
                app_state["mode"] = "🟢 运行中"

                if not session_start:
                    session_start = time.time()
                    print("[系统] >>> 获得操作授权，开始执行")

                # 检测状态变化
                if not last_allow_state:
                    is_first_action = True
                    print("[系统] 🎯 开始新会话")

                    # ✅ 操作次数 = 进入 operating 状态的次数
                    app_state["total_actions"] += 1
                    print(f"[统计] 操作次数 +1 → {app_state['total_actions']}")

                last_allow_state = True
                action_should_stop.clear()

                # 执行操作
                current_phase = 'normal'
                execute_move_interruptible(
                    phase=current_phase,
                    is_first=is_first_action,
                    reader=reader
                )
                
                # ⚠️ 移除：不再在每次按键后计数
                # 操作次数应该统计"进入operating的次数"，而不是"按键次数"
                
                is_first_action = False
                
                # 操作后休息
                rest_min, rest_max = REST_TIMES.get(current_phase, (REST_MIN, REST_MAX))
                rest_time = random.uniform(rest_min, rest_max)
                time.sleep(rest_time)
                
                # 重置错误计数
                consecutive_errors = 0
                
            else:
                # ❌ JS 端不允许，等待
                if session_start:
                    session_start = None
                    is_first_action = True
                    print("[系统] <<< 失去操作授权，停止执行")
                
                last_allow_state = False
                action_should_stop.set()
                safe_key_up_all()
                
                app_state["mode"] = "🔵 待机"
                app_state["status"] = "等待 JS 端授权..."
                app_state["phase"] = "待机"
                
                time.sleep(0.5)
            # ===========================================

        except Exception as e:
            print(f"[主循环错误] {e}")
            consecutive_errors += 1
            app_state["error_count"] = consecutive_errors
            app_state["last_error"] = str(e)[:30]
            write_python_heartbeat(last_error=str(e))
            
            action_should_stop.set()
            safe_key_up_all()
            
            if consecutive_errors >= max_consecutive_errors:
                print(f"[严重] 连续{consecutive_errors}次错误，等待10秒...")
                time.sleep(10)
                consecutive_errors = 0
            else:
                time.sleep(1)
            
            gc.collect()

    print("[系统] 主逻辑退出")
    write_python_heartbeat(running=False)

# ================= 🚀 启动入口 =================
if __name__ == "__main__":
    print("=" * 60)
    print("PRISMAX 智能控制系统 v2.5 - 跨端联动版")
    print("=" * 60)
    print("🎯 架构特性:")
    print("  • JS 端权威判断（DOM 检测）")
    print("  • Python 端纯执行（听从指令）")
    print("  • 状态实时同步（0.5秒延迟）")
    print("  • 零误触发风险")
    print("=" * 60)
    print("🔧 核心改动:")
    print("  ✅ 移除颜色/OCR独立检测")
    print("  ✅ 新增状态读取器（JS → Python）")
    print("  ✅ 只在 JS 授权时执行按键")
    print("  ✅ 操作过程中持续检测授权")
    print("=" * 60)
    print("🎮 快捷键:")
    print("  F9  - 启动/暂停")
    print("  ESC - 紧急停止")
    print("=" * 60)
    print("📋 前置要求:")
    print("  1. JS 端脚本已运行（Tampermonkey）")
    print("  2. requests、pygetwindow 已安装")
    print("  3. state_reader_http.py 在同目录")
    print("=" * 60)
    print()
    
    t = threading.Thread(target=bot_logic, daemon=False)
    t.start()
    
    try:
        SmartHUD()
    except Exception as e:
        print(f"[HUD错误] {e}")
        app_state["last_error"] = f"HUD: {e}"
        write_python_heartbeat(last_error=f"HUD: {e}")
        safe_key_up_all()
        print("[HUD错误] HUD 已退出，主控线程继续运行；请查看 supervisor 告警。")
        while bot_running:
            write_python_heartbeat()
            time.sleep(1)
