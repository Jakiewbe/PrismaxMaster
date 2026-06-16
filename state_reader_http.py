"""
PRISMAX 状态读取器 V2.0 - HTTP 优化版（错误处理增强）
支持两种读取方式：
1. HTTP接口读取（推荐，最快）
2. 文件读取（备用）
"""

import json
import time
import os
from datetime import datetime
import config_shared as cfg

# ================= 配置 =================
class ReaderConfig:
    # HTTP 接口配置
    BRIDGE_URL = f"http://{cfg.BRIDGE_HOST}:{cfg.BRIDGE_PORT}/state"
    USE_HTTP = True  # 优先使用 HTTP
    HTTP_TIMEOUT = cfg.HTTP_TIMEOUT  # HTTP 超时（秒）
    
    # 文件配置
    STATE_FILE = cfg.STATE_FILE
    USE_FILE = True  # 备用文件读取
    
    # 缓存配置
    CHECK_COOLDOWN = 0.3  # 检查冷却时间（秒）
    STATE_STALE_SECONDS = cfg.STATE_STALE_SECONDS
    HTTP_RETRY_INTERVAL = cfg.HTTP_RETRY_INTERVAL
    HTTP_MAX_CONSECUTIVE_FAILS = cfg.HTTP_MAX_CONSECUTIVE_FAILS
    
    # 调试
    DEBUG = cfg.DEBUG


# ================= 状态读取器 =================
class StateReader:
    """从 JS 端读取权威状态"""
    
    def __init__(self, config=None):
        self.config = config or ReaderConfig()
        self.last_state = {}
        self.last_check_time = 0
        self.http_available = None  # None=未测试, True=可用, False=不可用
        self.last_http_retry_time = 0
        self.http_retry_interval = self.config.HTTP_RETRY_INTERVAL
        self.consecutive_http_failures = 0
        self.max_http_failures = self.config.HTTP_MAX_CONSECUTIVE_FAILS  # 连续失败后切换到文件模式
        
        # 🆕 智能重连相关
        self.initial_retry_interval = 3   # 初始重试间隔（秒）
        self.max_retry_interval = 30      # 最大重试间隔（秒）
        self.retry_backoff_factor = 1.5   # 退避因子
        self.current_retry_interval = self.initial_retry_interval
        self.total_reconnect_attempts = 0
        
        self._log("状态读取器已初始化")
        self._test_connection()
    
    def _log(self, message):
        """调试日志"""
        if self.config.DEBUG:
            print(f"[状态读取器] {message}")
    
    def _test_connection(self):
        """测试与中转站的连接"""
        if not self.config.USE_HTTP:
            return
        
        try:
            import requests
            response = requests.get(
                f"{self.config.BRIDGE_URL.replace('/state', '')}/health",
                timeout=self.config.HTTP_TIMEOUT
            )
            
            if response.status_code == 200:
                self.http_available = True
                self._log("✅ HTTP 连接测试成功")
            else:
                self.http_available = False
                self._log("⚠️ HTTP 连接测试失败")
        except ImportError:
            print("[状态读取器] ⚠️ 未安装 requests 库")
            print("   安装命令: pip install requests")
            print("   将使用文件读取模式")
            self.http_available = False
            self.config.USE_HTTP = False
        except Exception as e:
            self.http_available = False
            self._log(f"⚠️ HTTP 连接测试异常: {e}")
            # 🆕 增加重试间隔（退避策略）
            self.current_retry_interval = min(
                self.current_retry_interval * self.retry_backoff_factor,
                self.max_retry_interval
            )
        finally:
            self.last_http_retry_time = time.time()
    
    def _calc_age_seconds(self, timestamp):
        """将时间戳转换为秒级差值，兼容秒/毫秒两种单位"""
        if not timestamp or timestamp <= 0:
            return None
        ts_seconds = timestamp / 1000.0 if timestamp > 1e12 else timestamp
        return time.time() - ts_seconds

    def _is_state_fresh_for_operation(self, state):
        """授权专用新鲜度检查。缓存状态只能用于显示，不能继续授权操作。"""
        if not state:
            return False

        if state.get('jsStatus') in ('stale', 'missing'):
            return False

        heartbeat_age = state.get('jsHeartbeatAge')
        if isinstance(heartbeat_age, (int, float)) and heartbeat_age > self.config.STATE_STALE_SECONDS:
            return False

        timestamp = state.get('loopHeartbeatAt') or state.get('timestamp')
        age_seconds = self._calc_age_seconds(timestamp)
        return age_seconds is not None and age_seconds <= self.config.STATE_STALE_SECONDS
    
    def read_state_from_http(self):
        """从 HTTP 接口读取状态（推荐）"""
        if not self.config.USE_HTTP or self.http_available == False:
            return None
        
        try:
            import requests
            
            response = requests.get(
                self.config.BRIDGE_URL,
                timeout=self.config.HTTP_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                state = data.get('data', {})
                
                # 检查时间戳是否过期（超过5秒认为过期）
                timestamp = data.get('timestamp')
                age_seconds = self._calc_age_seconds(timestamp)
                
                if age_seconds is not None and age_seconds > self.config.STATE_STALE_SECONDS:
                    self._log(f"⚠️ 状态过期（{age_seconds:.1f}秒前）")
                    return None
                
                # 重置失败计数
                if self.consecutive_http_failures > 0:
                    # 🆕 连接恢复提示
                    print(f"[状态读取器] ✅ HTTP 连接已恢复（之前失败 {self.consecutive_http_failures} 次）")
                self.consecutive_http_failures = 0
                self.http_available = True
                self.current_retry_interval = self.initial_retry_interval  # 🆕 重置重试间隔
                
                return state
            else:
                raise Exception(f"HTTP {response.status_code}")
        
        except Exception as e:
            self.consecutive_http_failures += 1
            
            # 连续失败多次后标记为不可用
            if self.consecutive_http_failures >= self.max_http_failures:
                if self.http_available != False:
                    print(f"[状态读取器] ❌ HTTP 连续失败 {self.max_http_failures} 次，切换到文件模式")
                    print("   请确保 Bridge.py 中转服务正在运行")
                self.http_available = False
            
            self._log(f"HTTP 读取失败: {e}")
            return None
    
    def read_state_from_file(self):
        """从文件读取状态（备用）"""
        if not self.config.USE_FILE:
            return None
        
        try:
            if not os.path.exists(self.config.STATE_FILE):
                return None
            
            with open(self.config.STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # 检查时间戳
            timestamp = state.get('timestamp')
            age_seconds = self._calc_age_seconds(timestamp)
            
            if age_seconds is not None and age_seconds > self.config.STATE_STALE_SECONDS:
                self._log(f"⚠️ 文件状态过期（{age_seconds:.1f}秒前）")
                return None
            
            return state
            
        except Exception as e:
            self._log(f"文件读取错误: {e}")
            return None
    
    def read_state(self):
        """
        读取状态（自动选择最佳方法）
        优先级：HTTP > 文件 > 缓存
        """
        # 检查冷却时间
        now = time.time()
        if now - self.last_check_time < self.config.CHECK_COOLDOWN:
            return self.last_state
        
        self.last_check_time = now
        
        # 方法1: 从 HTTP 读取（最快）
        if self.config.USE_HTTP and self.http_available != False:
            state = self.read_state_from_http()
            if state:
                self.last_state = state
                return state
        elif self.config.USE_HTTP and self.http_available == False:
            # HTTP 不可用时，智能间隔重试探测（🆕 使用退避策略）
            if now - self.last_http_retry_time >= self.current_retry_interval:
                self.total_reconnect_attempts += 1
                print(f"[状态读取器] 🔄 尝试重连 Bridge（第 {self.total_reconnect_attempts} 次，间隔 {self.current_retry_interval:.1f}s）")
                self._test_connection()
                if self.http_available:
                    self.total_reconnect_attempts = 0  # 成功后重置
        
        # 方法2: 从文件读取（备用）
        if self.config.USE_FILE:
            state = self.read_state_from_file()
            if state:
                self.last_state = state
                return state
        
        # 方法3: 使用缓存状态（最后备份）
        if self.last_state:
            self._log("⚠️ 使用缓存状态")
            return self.last_state
        
        # 无法读取状态
        return None
    
    def is_allowed_to_operate(self):
        """
        检查是否允许操作（核心函数）
        
        Returns:
            bool: True = 允许操作, False = 禁止操作
        """
        state = self.read_state()
        
        if not state:
            # 无法读取状态，默认禁止操作（安全起见）
            return False

        if not self._is_state_fresh_for_operation(state):
            return False
        
        # 检查 allowOperation 字段
        return state.get('allowOperation', False)
    
    def get_state_info(self):
        """获取详细状态信息（增强错误处理）"""
        state = self.read_state()
        
        if not state:
            return {
                'status': '❌ 无状态',
                'allow_operation': False,
                'is_operating': False,
                'is_queuing': False,
                'total_operations': 0,
                'anomaly_count': 0,
                'session_duration': 0,
                'connection_mode': 'none',
                'wallet_popup_active': False
            }
        
        # 判断连接模式
        if self.http_available:
            connection_mode = 'http'
        elif os.path.exists(self.config.STATE_FILE):
            connection_mode = 'file'
        else:
            connection_mode = 'cache'
        
        is_fresh = self._is_state_fresh_for_operation(state)
        return {
            'status': '🔴 JS过期' if not is_fresh
                     else '🟢 操作中' if state.get('isOperating') 
                     else '🔵 排队中' if state.get('isQueuing')
                     else '⚪ 待机中',
            'allow_operation': state.get('allowOperation', False) if is_fresh else False,
            'is_operating': state.get('isOperating', False),
            'is_queuing': state.get('isQueuing', False),
            'total_operations': state.get('totalOperations', 0),
            'anomaly_count': state.get('anomalyCount', 0),
            'session_duration': state.get('sessionDuration', 0),
            'rank': state.get('rank'),
            'performance_mode': state.get('performanceMode', 'unknown'),
            'connection_mode': connection_mode,
            'source': connection_mode,
            'http_failures': self.consecutive_http_failures,
            'wallet_popup_active': state.get('walletPopupActive', False)
        }
    
    def test_all_methods(self):
        """测试所有读取方式"""
        print("=" * 50)
        print("测试状态读取方式")
        print("=" * 50)
        
        # 测试 HTTP
        print("\n1. 测试 HTTP 读取...")
        http_state = self.read_state_from_http()
        if http_state:
            print("   ✅ HTTP 读取成功")
            print(f"   状态: {http_state.get('isOperating', 'unknown')}")
        else:
            print("   ❌ HTTP 读取失败")
            print("   提示: 请确保 Bridge_v2.py 正在运行")
            print("   运行命令: python Bridge_v2.py")
        
        # 测试文件
        print("\n2. 测试文件读取...")
        file_state = self.read_state_from_file()
        if file_state:
            print("   ✅ 文件读取成功")
            print(f"   状态: {file_state.get('isOperating', 'unknown')}")
        else:
            print("   ❌ 文件读取失败")
            print("   提示: 文件尚未生成或已过期")
        
        # 综合测试
        print("\n3. 综合测试（自动选择）...")
        state = self.read_state()
        if state:
            info = self.get_state_info()
            print(f"   ✅ 读取成功")
            print(f"   状态: {info['status']}")
            print(f"   授权: {'✅' if info['allow_operation'] else '❌'}")
            print(f"   方式: {info['connection_mode'].upper()}")
        else:
            print("   ❌ 读取失败")
            print("   ")
            print("   【故障排查】")
            print("   1. 确认 Bridge 正在运行:")
            print("      python Bridge_v2.py")
            print("   ")
            print("   2. 测试 Bridge 连接:")
            print("      curl http://127.0.0.1:5000/health")
            print("   ")
            print("   3. 检查浏览器 JS 脚本是否运行")
        
        print("\n" + "=" * 50)


# ================= 集成示例 =================
def main():
    """
    在你现有的 Python 脚本中集成
    """
    print("=" * 60)
    print("PRISMAX 状态读取器 V2.0 - HTTP 优化版")
    print("=" * 60)
    
    # 初始化状态读取器
    reader = StateReader()
    
    # 运行测试
    reader.test_all_methods()
    
    print("\n开始监控状态（按 Ctrl+C 停止）\n")
    
    try:
        while True:
            # 获取状态信息
            info = reader.get_state_info()
            
            # 显示状态
            mode_icon = "🚀" if info['connection_mode'] == 'http' else "📂" if info['connection_mode'] == 'file' else "❌"
            print(f"\r{mode_icon} {info['status']} | "
                  f"授权: {'✅' if info['allow_operation'] else '❌'} | "
                  f"操作: {info['total_operations']} 次 | "
                  f"模式: {info['connection_mode'].upper()}", end='', flush=True)
            
            # ========== 核心逻辑：只在允许时执行 ==========
            if reader.is_allowed_to_operate():
                # ✅ JS 端说可以操作，执行按键
                # execute_your_key_press()
                pass
            else:
                # ❌ JS 端说不能操作，等待
                pass
            # ===========================================
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\n测试结束")


if __name__ == "__main__":
    main()
