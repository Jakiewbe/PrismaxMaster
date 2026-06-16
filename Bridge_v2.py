"""
PRISMAX 状态中转服务器 v2.1 - 日志增强版
作用: 将浏览器 JS 端状态实时同步到本地，供 Python 端读取
新增: 事件日志记录功能
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import threading
import time
from datetime import datetime
from config_shared import (
    BRIDGE_HOST,
    BRIDGE_PORT,
    STATE_FILE,
    STATE_STALE_SECONDS,
    JS_HEARTBEAT_STALE_SECONDS,
    PYTHON_HEARTBEAT_STALE_SECONDS,
    PYTHON_HEARTBEAT_FILE,
)

# ================= 配置区域 =================
CONFIG = {
    'host': BRIDGE_HOST,
    'port': BRIDGE_PORT,
    'state_file': STATE_FILE,
    'enable_detailed_log': False,  # 详细日志（调试用）
    'enable_get_api': True,        # 启用 GET 接口（供 Python 端调用）
    'enable_stats': True,          # 启用统计信息
    'write_delay': 0.1,            # 写入延迟（秒），减少文件IO
    'heartbeat_timeout': JS_HEARTBEAT_STALE_SECONDS,  # JS 心跳超时（秒）
    # 🆕 日志系统配置
    'enable_event_log': True,      # 启用事件日志
    'log_dir': 'logs',             # 日志目录
    'log_max_size_mb': 10,         # 单个日志文件最大大小(MB)
    'log_keep_days': 7,            # 保留最近几天的日志
}

# ================= 全局状态 =================
file_lock = threading.Lock()
log_lock = threading.Lock()  # 🆕 日志文件锁
memory_cache = {}  # 内存缓存最新状态
pending_write = None  # 待写入数据
write_timer = None  # 写入定时器

stats = {
    'total_requests': 0,
    'success_count': 0,
    'error_count': 0,
    'last_update_time': 0,
    'last_heartbeat_warning_time': 0,
    'start_time': time.time(),
    'last_state': None,
    'events_logged': 0  # 🆕 记录的事件数
}

# ================= 工具函数 =================
def get_uptime():
    """获取运行时长"""
    uptime_seconds = int(time.time() - stats['start_time'])
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_js_health():
    """返回 JS 心跳健康状态。"""
    if stats['last_update_time'] <= 0:
        return {
            'js_status': 'missing',
            'js_heartbeat_age': None,
            'js_push_age': None,
            'main_loop_age': None,
            'is_fresh': False,
        }

    now = time.time()
    push_age = now - stats['last_update_time']
    loop_ts = memory_cache.get('loopHeartbeatAt') if isinstance(memory_cache, dict) else None
    loop_seconds = loop_ts / 1000.0 if loop_ts and loop_ts > 1e12 else loop_ts
    main_loop_age = now - loop_seconds if loop_seconds else push_age
    age = max(push_age, main_loop_age)
    is_fresh = push_age <= CONFIG['heartbeat_timeout'] and main_loop_age <= CONFIG['heartbeat_timeout']
    return {
        'js_status': 'fresh' if is_fresh else 'stale',
        'js_heartbeat_age': round(age, 2),
        'js_push_age': round(push_age, 2),
        'main_loop_age': round(main_loop_age, 2),
        'is_fresh': is_fresh,
    }

def get_python_health():
    """读取 Python 主控心跳文件，仅用于健康检查和 supervisor 提示。"""
    if not os.path.exists(PYTHON_HEARTBEAT_FILE):
        return {
            'python_status': 'missing',
            'python_heartbeat_age': None,
            'python_heartbeat': None,
        }

    try:
        with open(PYTHON_HEARTBEAT_FILE, 'r', encoding='utf-8') as f:
            heartbeat = json.load(f)
        last_ts = heartbeat.get('lastHeartbeatAt', 0)
        ts_seconds = last_ts / 1000.0 if last_ts and last_ts > 1e12 else last_ts
        age = time.time() - ts_seconds if ts_seconds else None
        status = 'fresh' if age is not None and age <= PYTHON_HEARTBEAT_STALE_SECONDS else 'stale'
        return {
            'python_status': status,
            'python_heartbeat_age': round(age, 2) if age is not None else None,
            'python_heartbeat': heartbeat,
        }
    except Exception as e:
        return {
            'python_status': 'error',
            'python_heartbeat_age': None,
            'python_heartbeat': {'lastError': str(e)},
        }

def get_public_state():
    """返回对下游安全的状态；JS 过期时强制撤销授权。"""
    state = memory_cache.copy() if isinstance(memory_cache, dict) else {}
    js_health = get_js_health()
    state['jsStatus'] = js_health['js_status']
    state['jsHeartbeatAge'] = js_health['js_heartbeat_age']
    if not js_health['is_fresh']:
        state['allowOperation'] = False
    return state

# ================= 🆕 日志系统 =================
def get_log_file_path():
    """获取当天日志文件路径"""
    today = datetime.now().strftime('%Y-%m-%d')
    log_dir = CONFIG['log_dir']
    
    # 确保日志目录存在
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    return os.path.join(log_dir, f'prismax_{today}.log')

def write_event_log(event_type, event_data, source='js'):
    """
    写入事件日志
    :param event_type: 事件类型 (operation_start, operation_end, anomaly, comment_task, morning, error 等)
    :param event_data: 事件数据 (dict)
    :param source: 来源 (js/python/bridge)
    """
    if not CONFIG['enable_event_log']:
        return
    
    try:
        log_entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': int(time.time() * 1000),
            'type': event_type,
            'source': source,
            'data': event_data
        }
        
        log_line = json.dumps(log_entry, ensure_ascii=False) + '\n'
        
        with log_lock:
            log_path = get_log_file_path()
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)
        
        stats['events_logged'] += 1
        
        if CONFIG['enable_detailed_log']:
            print(f"\n[日志] 已记录: {event_type}")
            
    except Exception as e:
        print(f"\n❌ [日志写入错误] {e}")

def cleanup_old_logs():
    """清理过期日志文件"""
    if not CONFIG['enable_event_log']:
        return
    
    try:
        log_dir = CONFIG['log_dir']
        if not os.path.exists(log_dir):
            return
        
        keep_days = CONFIG['log_keep_days']
        now = time.time()
        cutoff = now - (keep_days * 24 * 60 * 60)
        
        for filename in os.listdir(log_dir):
            if filename.startswith('prismax_') and filename.endswith('.log'):
                filepath = os.path.join(log_dir, filename)
                file_mtime = os.path.getmtime(filepath)
                if file_mtime < cutoff:
                    os.remove(filepath)
                    print(f"[日志] 已清理过期日志: {filename}")
    except Exception as e:
        print(f"\n❌ [日志清理错误] {e}")

def is_state_changed(new_state):
    """检查状态是否变化"""
    if not stats['last_state']:
        return True
    
    # 只比较关键字段
    key_fields = [
        'isOperating',
        'isQueuing',
        'allowOperation',
        'totalOperations',
        'anomalyCount',
        'sessionDuration'
    ]
    for field in key_fields:
        if new_state.get(field) != stats['last_state'].get(field):
            return True
    return False

def delayed_write():
    """延迟写入文件（减少IO）"""
    global pending_write, write_timer
    
    if pending_write is None:
        return
    
    try:
        with file_lock:
            with open(CONFIG['state_file'], 'w', encoding='utf-8') as f:
                json.dump(pending_write, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
        
        if CONFIG['enable_detailed_log']:
            print(f"\n[写入] 状态已保存到文件")
        
        pending_write = None
    except Exception as e:
        print(f"\n❌ [写入错误] {e}")
        stats['error_count'] += 1

def schedule_write(state_data):
    """安排写入任务"""
    global pending_write, write_timer
    
    pending_write = state_data
    
    # 取消之前的写入任务
    if write_timer:
        write_timer.cancel()
    
    # 创建新的延迟写入任务
    write_timer = threading.Timer(CONFIG['write_delay'], delayed_write)
    write_timer.daemon = True
    write_timer.start()

def check_heartbeat():
    """检查心跳超时"""
    while True:
        time.sleep(5)  # 每5秒检查一次
        
        if stats['last_update_time'] == 0:
            continue
        
        elapsed = time.time() - stats['last_update_time']
        
        if elapsed > CONFIG['heartbeat_timeout'] and time.time() - stats['last_heartbeat_warning_time'] >= 60:
            stats['last_heartbeat_warning_time'] = time.time()
            print(f"\n⚠️  [心跳超时] 已 {int(elapsed)} 秒未收到 JS 端数据")
            print("   可能原因: JS 端脚本未运行 / 浏览器已关闭")

# ================= HTTP 处理器 =================
class SyncHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """屏蔽默认日志"""
        if CONFIG['enable_detailed_log']:
            print(f"[请求] {format % args}")
    
    def do_OPTIONS(self):
        """处理跨域预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """处理 GET 请求（供 Python 端直接读取）"""
        if not CONFIG['enable_get_api']:
            self.send_error(403, "GET API is disabled")
            return
        
        try:
            path = self.path
            
            # 路由1: 获取状态
            if path == '/state' or path == '/':
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                # 从内存缓存读取
                public_state = get_public_state()
                response = {
                    'status': 'success',
                    'data': public_state,
                    'timestamp': public_state.get('timestamp', int(stats['last_update_time'] * 1000))
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
            
            # 路由2: 获取统计信息
            elif path == '/stats':
                if not CONFIG['enable_stats']:
                    self.send_error(403, "Stats API is disabled")
                    return
                
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                response = {
                    'total_requests': stats['total_requests'],
                    'success_count': stats['success_count'],
                    'error_count': stats['error_count'],
                    'success_rate': f"{stats['success_count'] / max(stats['total_requests'], 1) * 100:.1f}%",
                    'uptime': get_uptime(),
                    'last_update': datetime.fromtimestamp(stats['last_update_time']).strftime('%Y-%m-%d %H:%M:%S') if stats['last_update_time'] > 0 else 'Never'
                }
                self.wfile.write(json.dumps(response, indent=2).encode('utf-8'))
            
            # 路由3: 健康检查
            elif path == '/health':
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                js_health = get_js_health()
                python_health = get_python_health()
                public_state = get_public_state()
                latest_allow = memory_cache.get('allowOperation', False)
                latest_operating = memory_cache.get('isOperating', False)
                latest_queuing = memory_cache.get('isQueuing', False)
                
                response = {
                    'status': 'healthy' if js_health['is_fresh'] else 'timeout',
                    'bridge_alive': True,
                    'js_status': js_health['js_status'],
                    'js_heartbeat_age': js_health['js_heartbeat_age'],
                    'js_push_age': js_health['js_push_age'],
                    'main_loop_age': js_health['main_loop_age'],
                    'python_status': python_health['python_status'],
                    'python_heartbeat_age': python_health['python_heartbeat_age'],
                    'performance_mode': public_state.get('performanceMode', 'unknown'),
                    'last_update_seconds_ago': int(js_health['js_heartbeat_age'] or 999),
                    'allow_operation': latest_allow if js_health['is_fresh'] else False,
                    'is_operating': latest_operating,
                    'is_queuing': latest_queuing,
                    'timestamp': memory_cache.get('timestamp', 0),
                    'last_script_error': public_state.get('lastScriptError', ''),
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
            
            else:
                self.send_error(404, "Not Found")
        
        except Exception as e:
            print(f"\n❌ [GET错误] {e}")
            self.send_error(500, str(e))
    
    def do_POST(self):
        """处理来自 JS 的数据推送"""
        global memory_cache
        stats['total_requests'] += 1
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error(400, "Empty request")
                return
            
            # 读取数据
            post_data = self.rfile.read(content_length)
            raw_content = post_data.decode('utf-8')
            state_data = json.loads(raw_content)
            now_ts = time.time()
            state_data.setdefault('timestamp', int(now_ts * 1000))
            
            # 🆕 处理事件日志（如果有）
            if 'eventLog' in state_data:
                event_log = state_data.pop('eventLog')  # 移除日志字段，不存入状态
                if isinstance(event_log, dict):
                    write_event_log(
                        event_type=event_log.get('type', 'unknown'),
                        event_data=event_log.get('data', {}),
                        source='js'
                    )
                elif isinstance(event_log, list):
                    for event in event_log:
                        write_event_log(
                            event_type=event.get('type', 'unknown'),
                            event_data=event.get('data', {}),
                            source='js'
                        )
            
            # 🆕 自动检测状态变化并记录关键事件
            old_state = stats['last_state'] or {}
            
            # 操作开始
            if state_data.get('isOperating') and not old_state.get('isOperating'):
                write_event_log('operation_start', {
                    'totalOperations': state_data.get('totalOperations', 0),
                    'timestamp': state_data.get('timestamp')
                })
            
            # 操作结束
            if not state_data.get('isOperating') and old_state.get('isOperating'):
                session_duration = state_data.get('sessionDuration', 0)
                is_anomaly = session_duration < 40  # 小于40秒视为异常
                write_event_log('operation_end', {
                    'sessionDuration': session_duration,
                    'isAnomaly': is_anomaly,
                    'totalOperations': state_data.get('totalOperations', 0),
                    'anomalyCount': state_data.get('anomalyCount', 0)
                })
            
            # 更新内存缓存
            memory_cache = state_data
            stats['last_update_time'] = now_ts
            stats['success_count'] += 1
            
            # 检查状态是否变化
            state_changed = is_state_changed(state_data)
            stats['last_state'] = state_data.copy()
            
            # 延迟写入文件（减少IO）
            if state_changed:
                schedule_write(state_data)
                if CONFIG['enable_detailed_log']:
                    print(f"\n[变化] 状态已更新")
            
            # 返回响应
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "success"}')
            
            # 控制台输出
            status_icon = "🟢" if state_data.get('isOperating') else "🔵"
            status_text = "运行中" if state_data.get('isOperating') else "排队中" if state_data.get('isQueuing') else "待机"
            allow_icon = "✅" if state_data.get('allowOperation') else "❌"
            
            # 显示统计信息（🆕 添加日志计数）
            if CONFIG['enable_stats']:
                success_rate = stats['success_count'] / stats['total_requests'] * 100
                log_info = f" | 日志:{stats['events_logged']}" if CONFIG['enable_event_log'] else ""
                print(f"\r[中转站] {status_icon} {status_text} | 授权:{allow_icon} | 请求:{stats['total_requests']} | 成功率:{success_rate:.1f}%{log_info} | 运行:{get_uptime()}", end="", flush=True)
            else:
                print(f"\r[中转站] {status_icon} {status_text} | 授权:{allow_icon}", end="", flush=True)
        
        except json.JSONDecodeError:
            print("\n❌ [JSON错误] 接收到无效数据")
            stats['error_count'] += 1
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            print(f"\n❌ [处理错误] {e}")
            stats['error_count'] += 1
            self.send_error(500, str(e))

# ================= 主函数 =================
def run_bridge():
    """启动中转服务器"""
    try:
        # 🆕 初始化日志系统
        if CONFIG['enable_event_log']:
            cleanup_old_logs()  # 清理过期日志
            log_path = get_log_file_path()
            write_event_log('bridge_start', {
                'version': '2.1',
                'host': CONFIG['host'],
                'port': CONFIG['port']
            }, source='bridge')
        
        # 启动心跳检查线程
        heartbeat_thread = threading.Thread(target=check_heartbeat, daemon=True)
        heartbeat_thread.start()
        
        server_address = (CONFIG['host'], CONFIG['port'])
        try:
            httpd = HTTPServer(server_address, SyncHandler)
        except OSError as e:
            if getattr(e, 'winerror', None) == 10048 or getattr(e, 'errno', None) == 98 or 'Address already in use' in str(e):
                print(f"\n❌ 端口 {CONFIG['port']} 已被占用，请关闭占用程序或修改 config_shared.py 中 BRIDGE_PORT")
            else:
                print(f"\n❌ 绑定失败: {e}")
            return

        # 启动信息
        print("=" * 60)
        print("🚀 PRISMAX 状态中转服务器 v2.1 - 日志增强版")
        print("=" * 60)
        print(f"📡 监听地址: http://{CONFIG['host']}:{CONFIG['port']}")
        print(f"📂 状态文件: {CONFIG['state_file']}")
        if CONFIG['enable_event_log']:
            print(f"📝 日志目录: {CONFIG['log_dir']}/")
        print("")
        print("🔧 功能特性:")
        print(f"  • POST /       - 接收 JS 端状态推送")
        if CONFIG['enable_get_api']:
            print(f"  • GET /state   - 获取当前状态（供 Python 端调用）")
            print(f"  • GET /health  - 健康检查")
        if CONFIG['enable_stats']:
            print(f"  • GET /stats   - 获取统计信息")
        print("")
        print("⚙️  优化特性:")
        print(f"  • 内存缓存: 减少文件 IO")
        print(f"  • 延迟写入: {CONFIG['write_delay']}秒批量写入")
        print(f"  • 心跳检测: {CONFIG['heartbeat_timeout']}秒超时警告")
        print(f"  • 变化检测: 只在状态变化时写入")
        if CONFIG['enable_event_log']:
            print(f"  • 🆕 事件日志: 自动记录操作/异常事件")
            print(f"  • 🆕 日志保留: {CONFIG['log_keep_days']}天")
        print("=" * 60)
        print("💡 提示: 按 Ctrl+C 停止服务")
        print("=" * 60)
        print("")
        
        # 启动服务器
        httpd.serve_forever()
    
    except KeyboardInterrupt:
        if CONFIG['enable_event_log']:
            write_event_log('bridge_stop', {'reason': 'user_interrupt'}, source='bridge')
        print("\n\n🛑 服务器已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")

if __name__ == "__main__":
    run_bridge()
