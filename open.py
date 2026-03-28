import sys
import os
import json
import requests
import urllib.request
import urllib.error
import random
import string
import time
import re
import quopri
import argparse
import secrets
import hashlib
import base64
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    HAS_GUI = True
except (ImportError, RuntimeError):
    # 在 VPS/容器环境 (没有 X11/Tk) 会走到这里
    HAS_GUI = False
import threading
from datetime import datetime, timedelta, timezone
from typing import Tuple, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs, urljoin, quote, urlencode
import socket
import subprocess
import imaplib
from email import message_from_string
from email.header import decode_header, make_header
from email.message import Message
from email.policy import default as email_policy
import email as email_lib

# ==========================================
# 0. 环境自检与依赖安装
# ==========================================

def _check_dependencies():
    """检查并安装缺失的依赖库"""
    required_packages = ["curl_cffi", "requests", "socks"]
    for package in required_packages:
        package_check = package
        if package == "socks": # PySocks 库对应模块名为 socks
            package_check = "socks"
        try:
            __import__(package_check)
        except ImportError:
            print(f"[*] 检测到缺失依赖: {package}，正在自动安装...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"[+] {package} 安装成功。")
            except Exception as e:
                print(f"[-] 安装 {package} 失败: {e}")
                print(f"[!] 请手动运行: pip install {package}")
                sys.exit(1)

_check_dependencies()

# --- 环境依赖预检 ---
_check_dependencies()
from curl_cffi import requests

# --- 根目录定位与配置加载（分段策略） ---
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 预读 RUN_MODE 标识 (为了决定下一步是否载入 GUI 向导)
_ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
def _pre_detect_vps_flag() -> bool:
    """快速嗅探环境：1 为 VPS, 0 为本地"""
    if not os.path.exists(_ENV_PATH): return False
    try:
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            return "RUN_MODE=1" in content
    except: return False

IS_VPS_RUN = _pre_detect_vps_flag() or (not HAS_GUI)

from curl_cffi import requests

# 动态获取根目录（兼容原生独立运行与 PyInstaller 最终编译打包出单执行文件环境）
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ==========================================
# 1. 环境配置与 OAuth 核心
# ==========================================

class OAuthConfiguration:
    def __init__(self) -> None:
        self.client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann"
        self.redirect_uri: str = "http://localhost:1455/auth/callback"
        self.scope: str = "openid email profile offline_access"
        self.state: str = ""
        self.code_verifier: str = ""
        self.code_challenge: str = ""

    def generate_pkad_params(self) -> Tuple[str, str]:
        self.code_verifier = secrets.token_urlsafe(94)[:128]
        digest = hashlib.sha256(self.code_verifier.encode("ascii")).digest()
        b64 = base64.urlsafe_b64encode(digest).decode()
        self.code_challenge = b64.rstrip("=")
        return self.code_verifier, self.code_challenge

def _save_to_dotenv(key: str, value: str) -> None:
    """将配置项保存或更新到 .env 文件中"""
    path = os.path.join(SCRIPT_DIR, ".env")
    lines = []
    found = False
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"{key}={value}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

def _check_proxy_alive(proxy_url: str) -> bool:
    """探测代理端口是否连通"""
    if not proxy_url: return True
    try:
        parsed = urlparse(proxy_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port
        if not port: return True
        with socket.create_connection((host, port), timeout=2):
            return True
    except Exception:
        return False

def _format_proxy(val: str) -> str:
    """将纯端口号或简写补全为标准的 http 代理格式"""
    val = val.strip()
    if not val: return ""
    if val.isdigit():
        return f"http://127.0.0.1:{val}"
    if ":" in val and not val.startswith("http"):
        return f"http://{val}"
    return val

def show_config_wizard(path: str, is_edit: bool = False, parent = None) -> bool:
    """显示配置向导弹窗"""
    import tkinter as tk
    from tkinter import ttk, messagebox
    
    # 如果是编辑模式，使用 Toplevel 否则新建 Tk
    cfg_root = tk.Toplevel(parent) if parent else tk.Tk()
    cfg_root.title("参数配置向导" if not is_edit else "编辑系统配置")
    cfg_root.geometry("550x650") # 增加高度以容纳更多字段
    if parent: cfg_root.grab_set() # 模态窗
    
    # 尝试加载图标
    try:
        icon_path = os.path.join(SCRIPT_DIR, "openai.ico")
        if os.path.exists(icon_path): cfg_root.iconbitmap(icon_path)
    except Exception: pass
    
    title_text = "请填写以下信息配置系统：" if not is_edit else "修改 .env 配置文件："
    ttk.Label(cfg_root, text=title_text, font=("Arial", 11, "bold")).pack(pady=5)
    
    # 容器：Canvas + Scrollbar (解决字段过多导致按钮被遮挡的问题)
    container = ttk.Frame(cfg_root)
    container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=515) # 稍微窄一点避开滚动条
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # 鼠标滚轮支持
    def _on_mousewheel(event):
        try:
            if cfg_root.winfo_exists():
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        except Exception:
            pass
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    frame = scrollable_frame

    # 定义配置项及其描述，用于生成带注释的 .env (对齐 env.example)
    configs = [
        ("SECTION_PUBLIC", "🌌 [公共区域] 核心账号与注册策略", None),
        ("RUN_MODE", "运行模式: 0=本机模式, 1=VPS服务器模式", "0"),
        ("CPA_UPLOAD_ENABLED", "CPA 上传接口开关 (0:关 1:开)", "1"),
        ("CPA_USE_PROXY", "CPA 上传独立走代理 (推荐 0:直连)", "0"), # 新增 UI
        ("CPA_API_URL", "CPA 上传接口 URL", "https://cpa.example.com/v0/management/auth-files"),
        ("CPA_API_TOKEN", "CPA 鉴权 Token", ""),
        ("IMAP_USER", "IMAP 收件箱账号 (必需)", ""),
        ("IMAP_PASS", "IMAP 专用密码 (必需)", ""),
        ("EMAIL_LIST", "裂变主邮箱列表 (逗号分隔)", ""),
        ("TAG_LENGTH", "裂变标签长度 (默认8)", "8"),
        ("TOKEN_OUTPUT_DIR", "成功凭据保存目录", "credentials"),
        
        ("SECTION_LOCAL", "🖥️ [本机配置] 注册任务与网络环境", None),
        ("PROXY_ENABLED", "代理网络开关 (0:关 1:开)", "1"),
        ("PROXY", "代理地址 (http://127.0.0.1:10808)", "http://127.0.0.1:10808"),
        ("THREAD_COUNT", "并发线程数", "1"),
        ("TARGET_SUCCESS_COUNT", "目标成功数 (不限设9999)", "100"),
        
        ("SECTION_VPS", "🚀 [VPS 配置] 自动化巡检与仓库补货", None),
        ("CPA_MAINTENANCE_ENABLED", "巡检引擎开关 (RUN_MODE=1有效)", "1"),
        ("MIN_ACCOUNTS_THRESHOLD", "库存补货最低水位", "15"),
        ("CHECK_INTERVAL_MINUTES", "巡检间隔 (分钟)", "30"),
        ("COOL_DOWN_HOURS", "注册冷却周期 (小时)", "24"),
        ("CPA_CLEAN_DEAD", "自动清理死号 (0:关 1:开)", "1"),
    ]

    entries = {}
    
    # 尝试读取旧值
    current_vals = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    current_vals[k.strip()] = v.strip().strip('"').strip("'")

    for idx, (key, prompt_text, default_val) in enumerate(configs):
        if key.startswith("SECTION_"):
            ttk.Label(frame, text=f"\n{prompt_text}", foreground="#85C1E9", font=("Consolas", 10, "bold")).grid(row=idx, column=0, columnspan=2, sticky=tk.W, pady=(5, 5), padx=10)
            continue
            
        ttk.Label(frame, text=prompt_text + " :").grid(row=idx, column=0, sticky=tk.E, pady=5, padx=5)
        display_val = current_vals.get(key, default_val)
        
        # 兼容性 Key 处理（如果是旧配置升级到新配置）
        if not current_vals.get(key):
            if key == "TAG_LENGTH": display_val = current_vals.get("GMAIL_TAG_LEN", default_val)
        
        if key in ["RUN_MODE", "PROXY_ENABLED", "CPA_UPLOAD_ENABLED", "CPA_USE_PROXY", "CPA_MAINTENANCE_ENABLED", "CPA_CLEAN_DEAD"]:
            ent = ttk.Combobox(frame, width=33, values=["0", "1"], state="readonly")
            ent.set(display_val)
        else:
            ent = ttk.Entry(frame, width=35)
            ent.insert(0, display_val)
        ent.grid(row=idx, column=1, sticky=tk.W, pady=5)
        entries[key] = ent
        
    def on_save():
        file_buffer = []
        file_buffer.append("# ==========================================")
        file_buffer.append(f"# OpenAI 自动注册系统配置 - 优化排版版")
        file_buffer.append(f"# 最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        file_buffer.append("# ==========================================\n")
        
        for key, prompt, _ in configs:
            if key.startswith("SECTION_"):
                header = f"\n# {'='*42}\n# {prompt}\n# {'='*42}"
                file_buffer.append(header)
                continue
            
            val = entries[key].get().strip()
            # 写入带中文注释的键值对
            file_buffer.append(f"# {prompt}")
            file_buffer.append(f"{key}={val}")
        
        file_buffer.append("\n# 内部专用强制校验")
        file_buffer.append("OPENAI_SSL_VERIFY=1")
        
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(file_buffer) + "\n")
        
        messagebox.showinfo("成功", "配置文件已按照最新结构化模板保存并美化！", parent=cfg_root)
        try: cfg_root.unbind_all("<MouseWheel>")
        except: pass
        cfg_root.destroy()
        if not parent: cfg_root.quit()

    def on_pull():
        """从 .env 文件中重新加载并填入界面"""
        if not os.path.exists(path):
            messagebox.showwarning("提示", "配置文件不存在，无法拉取！", parent=cfg_root)
            return
        new_vals = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    new_vals[k.strip()] = v.strip().strip('"').strip("'")
        
        for key, ent in entries.items():
            if key in new_vals:
                if isinstance(ent, ttk.Combobox):
                    ent.set(new_vals[key])
                else:
                    ent.delete(0, tk.END)
                    ent.insert(0, new_vals[key])
        messagebox.showinfo("成功", "已从 .env 文件拉取最新配置！", parent=cfg_root)
        
    def on_test_cpa():
        """测试 CPA 接口连通性"""
        url = entries.get("CPA_API_URL").get().strip()
        token = entries.get("CPA_API_TOKEN").get().strip()
        cpa_proxy = entries.get("CPA_USE_PROXY").get().strip()
        proxy_v = entries.get("PROXY").get().strip()
        
        if not url:
            messagebox.showerror("错误", "请先填写 CPA 上传接口 URL", parent=cfg_root)
            return

        # 临时覆盖全局变量以便 upload_to_cpa 使用界面值
        global CPA_API_URL, CPA_API_TOKEN, CPA_USE_PROXY, PROXY
        old_url, old_token = CPA_API_URL, CPA_API_TOKEN
        old_cp, old_pv = CPA_USE_PROXY, PROXY
        
        CPA_API_URL = url
        CPA_API_TOKEN = token
        CPA_USE_PROXY = (cpa_proxy == "1")
        PROXY = proxy_v
        
        test_file = "ceshi.json"
        test_content = json.dumps({"test_id": "cpa_check", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        
        try:
            # 在本地创建一个符合 CPA 规范的 .json 测试文件
            with open(test_file, "w", encoding="utf-8") as f: 
                f.write(test_content)
            
            # 使用加固后的上传逻辑测试 (含浏览器指纹模拟与直连自愈验证)
            success = upload_to_cpa("cpa_test_node", "debug", test_content, custom_filename=test_file)
            
            if success:
                messagebox.showinfo("测试成功", "✅ CPA 接口连通性测试通过！\n测试文件已成功入库并清理。", parent=cfg_root)
            else:
                messagebox.showerror("测试失败", "❌ 连通性测试失败！\n请检查 URL、Token 或网络环境 (查看控制台报错)。", parent=cfg_root)
        except Exception as e:
            messagebox.showerror("异常", f"测试过程发生错误: {e}", parent=cfg_root)
        finally:
            if os.path.exists(test_file): 
                try: os.remove(test_file)
                except: pass
            # 恢复之前的正式环境配置
            CPA_API_URL, CPA_API_TOKEN = old_url, old_token
            PROXY_ENABLED, PROXY = old_pe, old_pv

    def on_close():
        try: cfg_root.unbind_all("<MouseWheel>")
        except: pass
        cfg_root.destroy()
        if not parent: cfg_root.quit()

    cfg_root.protocol("WM_DELETE_WINDOW", on_close)

    btn_frame = ttk.Frame(cfg_root)
    btn_frame.pack(pady=15)

    ttk.Button(btn_frame, text="✅ 保存配置并继续", command=on_save).pack(side=tk.LEFT, padx=10)
    ttk.Button(btn_frame, text="🧪 测试 CPA 连通性", command=on_test_cpa).pack(side=tk.LEFT, padx=10)
    ttk.Button(btn_frame, text="🔄 从本地拉取文本配置", command=on_pull).pack(side=tk.LEFT, padx=10)

    btn_text = "💾 保存配置与启动" if not is_edit else "💾 保存当前修改"
    ttk.Button(btn_frame, text=btn_text, command=on_save).pack(side=tk.LEFT, padx=10)
    
    if not parent:
        cfg_root.mainloop()
        return os.path.exists(path)
    return True

def _load_dotenv(path: str = None) -> None:
    """加载 .env 文件。根据环境自动决策：本地环境下若缺失则引导向导，服务器环境下若缺失则初始化默认值"""
    if path is None:
        path = os.path.join(SCRIPT_DIR, ".env")
    
    if not os.path.exists(path):
        if HAS_GUI and not IS_VPS_RUN:
            # 本地 GUI 友好环境：弹出图形向导
            if not show_config_wizard(path):
                sys.exit(0)
        else:
            # 服务器 VPS 模式或无 X11 环境：静默生成默认配置而不报错
            # 注意：VPS 环境下用户通常会手动编辑该文件，此举仅为防止逻辑崩溃
            default_conf = [
                "# OpenAI 自动注册系统 - VPS 默认配置模版",
                "RUN_MODE=1", "PROXY_ENABLED=0", "PROXY=", "CPA_UPLOAD_ENABLED=0",
                "MIN_ACCOUNTS_THRESHOLD=15", "CHECK_INTERVAL_MINUTES=30",
                "TARGET_SUCCESS_COUNT=1", "THREAD_COUNT=1", "GMAIL_TAG_LEN=8",
                "IMAP_USER=", "IMAP_PASS="
            ]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(default_conf))
            print("[!] 系统警告: 检测到 VPS 下加载路径缺失配置文件 (.env)。已自动创建默认配置。")
            print("[!] 请根据需要编辑该文件并重新启动。")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                key, value = line.split("=", 1)
                key = key.strip(); value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}: value = value[1:-1]
                os.environ[key] = value
    except Exception as e:
        print(f"[-] 环境参数载入系统异常: {e}")

def reload_all_configs():
    """将环境变量统一加载并解析到全局变量中，确保逻辑一致性"""
    global TOKEN_OUTPUT_DIR, EMAIL_LIST, IMAP_USER, IMAP_PASS, CPA_API_URL, CPA_API_TOKEN
    global GMAIL_TAG_LEN, COOL_DOWN_HOURS, RUN_MODE, PROXY_ENABLED, PROXY
    global THREAD_COUNT, TARGET_SUCCESS_COUNT, CPA_MAINTENANCE_ENABLED, MIN_ACCOUNTS_THRESHOLD
    global BATCH_REG_COUNT, CHECK_INTERVAL_MINUTES, CPA_CLEAN_DEAD, CPA_UPLOAD_ENABLED, CPA_USE_PROXY
    
    TOKEN_OUTPUT_DIR = os.getenv("TOKEN_OUTPUT_DIR", "credentials").strip()
    if not os.path.isabs(TOKEN_OUTPUT_DIR):
        TOKEN_OUTPUT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, TOKEN_OUTPUT_DIR))
    
    RUN_MODE = int(os.getenv("RUN_MODE", "0"))
    PROXY_ENABLED = int(os.getenv("PROXY_ENABLED", "1"))
    PROXY = os.getenv("PROXY", "").strip() if PROXY_ENABLED else ""
    
    # 线程与成功数设置
    THREAD_COUNT = int(os.getenv("THREAD_COUNT", "1"))
    TARGET_SUCCESS_COUNT = int(os.getenv("TARGET_SUCCESS_COUNT", "999999"))
    
    raw_emails = os.getenv("EMAIL_LIST", "").strip()
    EMAIL_LIST = []
    for part in raw_emails.replace(",", " ").split():
        if "@" in part or "." in part:
            if "----" in part:
                e, p = part.split("----", 1)
                EMAIL_LIST.append({"email": e.strip(), "pass": p.strip()})
            else:
                EMAIL_LIST.append({"email": part.strip(), "pass": None})
    
    IMAP_USER = os.getenv("IMAP_USER", "").strip()
    IMAP_PASS = os.getenv("IMAP_PASS", "").strip()
    
    # CPA 运维设置 (支持兼容性 Key)
    CPA_UPLOAD_ENABLED = os.getenv("CPA_UPLOAD_ENABLED", "0") == "1"
    CPA_USE_PROXY = os.getenv("CPA_USE_PROXY", "0") == "1" # 新增
    CPA_MAINTENANCE_ENABLED = os.getenv("CPA_MAINTENANCE_ENABLED", "0") == "1"
    MIN_ACCOUNTS_THRESHOLD = int(os.getenv("MIN_ACCOUNTS_THRESHOLD", os.getenv("REPLENISH_THRESHOLD", "15")))
    CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", os.getenv("CHECK_INTERVAL", "30")))
    CPA_CLEAN_DEAD = os.getenv("CPA_CLEAN_DEAD", os.getenv("PHYSICAL_DELETE_DEAD", "0")) == "1"
    CPA_API_URL = os.getenv("CPA_API_URL", os.getenv("CPA_UPLOAD_URL", "")).strip()
    CPA_API_TOKEN = os.getenv("CPA_API_TOKEN", "").strip()

    # 策略设置 (支持兼容性 Key)
    GMAIL_TAG_LEN = int(os.getenv("TAG_LENGTH", os.getenv("GMAIL_TAG_LEN", "8")))
    COOL_DOWN_HOURS = int(os.getenv("COOL_DOWN_HOURS", "24"))
    BATCH_REG_COUNT = int(os.getenv("BATCH_REG_COUNT", "5"))


# ==========================================
# 1.4 主邮箱轮转状态 (顺序轮转, 持久化)
# ==========================================

_email_index = 0  # 全局轮转指针
_EMAIL_INDEX_FILE = os.path.join(SCRIPT_DIR, ".last_email_index")

def _load_email_index():
    """从磁盘加载上次使用的邮箱下标"""
    global _email_index
    try:
        if os.path.exists(_EMAIL_INDEX_FILE):
            with open(_EMAIL_INDEX_FILE, "r") as f:
                _email_index = int(f.read().strip())
    except Exception:
        _email_index = 0

def _save_email_index(idx: int):
    """将当前使用的下标持久化到磁盘"""
    try:
        with open(_EMAIL_INDEX_FILE, "w") as f:
            f.write(str(idx))
    except Exception:
        pass

_index_lock = threading.Lock()

def _pick_next_master():
    """顺序轮转选择主邮箱，跳过黑名单中的账号，下标持久化"""
    global _email_index
    if not EMAIL_LIST:
        return None
    with _index_lock:
        total = len(EMAIL_LIST)
        for _ in range(total):  # 最多尝试一轮
            idx = _email_index % total
            _email_index = (idx + 1) % total
            candidate = EMAIL_LIST[idx]
            if not blacklist_mgr.is_in_jail(candidate):
                _save_email_index(_email_index)  # 记住下一个将用的
                return candidate
    return None  # 全部都在黑名单中

# ==========================================
# 1.5 邮箱黑名单/冷却管理 (Anti-40x)
# ==========================================

class BlacklistManager:
    """管理邮箱冷却时间 (针对 403/40 错误代码)"""
    def __init__(self, path: str = None):
        if path is None:
            path = os.path.join(SCRIPT_DIR, "blacklist.json")
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, str]:
        if not os.path.exists(self.path): return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: return {}

    def _save(self, data: Dict[str, str]):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception: pass

    def is_in_jail(self, email: str) -> bool:
        """检查邮箱是否在冷却期"""
        target = email
        if isinstance(email, dict): target = email.get("email", "")
        with self._lock:
            data = self._load()
            expiry_str = data.get(target)
            if not expiry_str: return False
            try:
                expiry = datetime.fromisoformat(expiry_str)
                return datetime.now() < expiry
            except Exception: return False

    def put_in_jail(self, email: str, hours: int):
        """将邮箱放入黑名单冷却"""
        target = email
        if isinstance(email, dict): target = email.get("email", "")
        with self._lock:
            data = self._load()
            expiry = datetime.now() + timedelta(hours=hours)
            data[target] = expiry.isoformat()
            self._save(data)
            print(f"[!] 邮箱 {target} 进入冷却期 ({hours} 小时)")

blacklist_mgr = BlacklistManager()

def _generate_fission_email(master_email: str, tag_len: int) -> str:
    """根据主邮箱类型自动识别并执行最优裂变策略 (自动判断)"""
    if "@" not in master_email:
        # 如果主邮箱本身就不合规，退化回随机 6 字符 (适配 catch-all 域名模式)
        tag = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{tag}@{master_email}" if "." in master_email else f"{tag}@example.com"

    user, domain = master_email.split("@")
    is_gmail = "gmail.com" in domain or "googlemail.com" in domain
    tag = "".join(random.choices(string.ascii_lowercase + string.digits, k=tag_len))
    
    if is_gmail:
        # 对 Gmail 随机采用 Plus (+) 裂变或 Googlemail 后缀切换 (1 和 3 模式)
        strategy = random.choice(["plus", "googlemail"])
        
        if strategy == "googlemail":
            # 自动切换到 googlemail.com 域名
            return f"{user}+{tag}@googlemail.com"
            
        else:
            # 标准 Plus 模式
            return f"{user}+{tag}@{domain}"
    else:
        # 域/Catch-all 模式: 采用随机生成的前缀
        prefix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{prefix}@{domain}"

_load_dotenv()
reload_all_configs()
_load_email_index()

AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"

def _ssl_verify() -> bool:
    flag = os.getenv("OPENAI_SSL_VERIFY", "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}

def _append_line(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line.rstrip("\n") + "\n")

def upload_to_cpa(email: str, password: str, token_json_str: str, custom_filename: str = None) -> bool:
    """将获取到的账号、密码和 Token JSON 上传至 CPA API
    
    NOTE: 切换 curl_cffi 以绕过 Cloudflare 的原生 requests 拦截
    """
    if not CPA_API_URL or not CPA_API_TOKEN:
        return False

    log_cpa(f"[*] 正在尝试上传凭据至 CPA ({email})...")
    
    import secrets
    import time
    from curl_cffi import requests as crequests
    
    file_name = custom_filename or f"token_{email.replace('@', '_').replace('.', '_')}.json"
    
    # URL 路径对齐与协议提取
    raw_url = CPA_API_URL.strip()
    if raw_url.startswith("tps://"): raw_url = "https://" + raw_url[6:]
    elif raw_url.startswith("ttps://"): raw_url = "https://" + raw_url[7:]
    
    def _build_final_url(url: str):
        url = url.strip().rstrip("/")
        if not url.startswith("http"): url = "https://" + url
        if not url.endswith("/v0/management/auth-files"):
            from urllib.parse import urlparse
            p = urlparse(url)
            url = f"{p.scheme}://{p.netloc}/v0/management/auth-files"
        return url

    target_url = _build_final_url(raw_url)

    headers = {
        "Authorization": f"Bearer {CPA_API_TOKEN}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache"
    }
    
    # 构造最高拟拟真报文流
    boundary = "----WebKitFormBoundary" + secrets.token_hex(12)
    body_payload = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{token_json_str if isinstance(token_json_str, str) else token_json_str.decode('utf-8')}\r\n"
        f"--{boundary}--\r\n"
    ).encode('utf-8')
    
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    headers["Content-Length"] = str(len(body_payload))
    
    def _do_post(url: str, force_proxy: bool):
        # 严格遵守：如果强制指定不带代理，则绝不带代理 (解决 Connection Reset 问题)
        proxy_config = {"http": PROXY, "https": PROXY} if (force_proxy and PROXY) else None
        return crequests.post(
            url, headers=headers, data=body_payload,
            proxies=proxy_config, verify=_ssl_verify(),
            timeout=30, impersonate="chrome123"
        )

    try:
        # 核心逻辑：首跳线路严格遵从 CPA_USE_PROXY 用户配置
        # 这样即使全局代理开着，CPA 上传也能独立直连，完美解决回环 reset
        resp = _do_post(target_url, force_proxy=CPA_USE_PROXY)
        
        # 拦截容错 (仅在极度失败时触发一次反向纠偏尝试)
        if resp.status_code in [521, 403, 502, 504]:
            log_cpa(f"[!] 线路拦截 (HTTP {resp.status_code})，正在启动线路自动纠偏回源...")
            # 如果之前是走代理失败，则切直连；反之亦然
            resp = _do_post(target_url, force_proxy=not CPA_USE_PROXY)
            
            # 协议降级自愈逻辑保留
            if resp.status_code == 521 and target_url.startswith("https"):
                fallback_url = "http" + target_url[5:]
                resp = _do_post(fallback_url, force_proxy=False)
            
        if resp.status_code in [200, 201]:
            log_cpa(f"[+] 接口通达成功: {email} ({resp.status_code})")
            return True
        else:
            log_cpa(f"[-] CPA 拒收: HTTP {resp.status_code} - {resp.text[:100]}")
            return False
                
    except Exception as e:
        log_cpa(f"[-] 环境异常: {e}，尝试直连逃生...")
        try:
            resp = _do_post(target_url, use_proxy=False)
            if resp.status_code in [200, 201]: return True
        except: pass
        log_cpa(f"[-] CPA 连接彻底中断。")
        return False
                
    except Exception as e:
        log_cpa(f"[-] 环境异常，尝试终极直连自愈...")
        try:
            resp = _do_post(use_proxy=False)
            if resp.status_code in [200, 201]:
                return True
        except: pass
        log_cpa(f"[-] CPA 连接性中断: {e}")
        return False
                
    except Exception as e:
        log_cpa(f"[-] 对接 CPA 失败，触发终极直连兜底尝试...")
        try:
            resp = _do_post(use_proxy=False)
            if resp.status_code in [200, 201]:
                log_cpa(f"[+] 入库成功 (经直连自愈)!")
                return True
        except: pass
        log_cpa(f"[-] CPA 连接性彻底中断: {e}")
        return False
                
    except Exception as e:
        log_cpa(f"[-] 对接 CPA 失败，触发终极直连兜底...")
        try:
            resp = _do_post(use_proxy=False)
            if resp.status_code in [200, 201]:
                log_cpa(f"[+] 经自愈自适应，入库成功!")
                return True
        except: pass
        log_cpa(f"[-] CPA 连通性彻底中断: {e}")
        return False

                
    except Exception as e:
        log_cpa(f"[-] 对接 CPA 发生意外异常: {e}")
        return False





class CPAManager:
    """CPA API 智控核心"""
    def __init__(self, api_url: str, api_token: str):
        # 智能处理 URL：防止用户填写了完整的 auth-files 路径导致拼接出 404
        url = api_url.strip().rstrip("/")
        for suffix in ["/auth-files", "/api-call", "/auth-files/download"]:
            if url.endswith(suffix):
                url = url[:-len(suffix)]
        
        if "/v0/management" not in url:
            url = url.rstrip("/") + "/v0/management"
            
        self.api_url = url
        self.api_token = api_token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/"
        }

    def list_accounts(self) -> List[Dict]:
        try:
            url = f"{self.api_url}/auth-files"
            r = requests.get(url, headers=self._headers(), timeout=20)
            if r.status_code == 200:
                files = r.json().get("files", [])
                # 仅筛选 codex 账号
                return [f for f in files if "codex" in str(f.get("type","")).lower() or "codex" in str(f.get("provider","")).lower()]
            print(f"[-] CPA 获取账号列表失败: HTTP {r.status_code} - {r.text[:100]}")
            return []
        except Exception as e:
            print(f"[-] CPA 连接异常 (L): {e}")
            return []

    def download_data(self, name: str) -> Dict:
        try:
            url = f"{self.api_url}/auth-files/download"
            r = requests.get(url, params={"name": name}, headers=self._headers(), timeout=20)
            return r.json() if r.status_code == 200 else {}
        except Exception: return {}

    def test_health(self, auth_index: int, account_id: str = "") -> Tuple[bool, str]:
        """测活通过 api-call 全量模拟查询"""
        url = f"{self.api_url}/api-call"
        payload = {
            "authIndex": auth_index, "method": "GET", 
            "url": "https://chatgpt.com/backend-api/wham/usage",
            "header": {
                "Authorization": "Bearer $TOKEN$", 
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Chatgpt-Account-Id": str(account_id or "")
            }
        }
        try:
            r = requests.post(url, headers=self._headers(), json=payload, timeout=45)
            if r.status_code != 200: return False, f"CPA 接口 {r.status_code}"
            data = r.json()
            inner_code = data.get("status_code", 0)
            if inner_code >= 400:
                body = str(data.get("body", ""))
                if "usage_limit_reached" in body: return False, "Overlimit"
                return False, f"OpenAI {inner_code}"
            return True, "Healthy"
        except Exception: return False, "Timeout"

    def set_status(self, name: str, disabled: bool) -> bool:
        """启用或禁用凭据"""
        try:
            url = f"{self.api_url}/auth-files"
            r = requests.post(url, headers=self._headers(), json={"name": name, "disabled": disabled}, timeout=30)
            return r.status_code == 200
        except Exception: return False

    def delete_account(self, name: str) -> bool:
        try:
            url = f"{self.api_url}/auth-files"
            r = requests.delete(url, headers=self._headers(), params={"name": name}, timeout=30)
            return r.status_code == 200
        except Exception: return False

class MaintenanceTask:
    """CPA 自动化维护任务处理器"""
    def __init__(self):
        self.cpa = CPAManager(CPA_API_URL, CPA_API_TOKEN)
        self.is_running = False

    def start(self):
        if not CPA_MAINTENANCE_ENABLED: return
        if RUN_MODE != 1:
            # 彻底静默本地巡检逻辑
            return
        self.is_running = True
        threading.Thread(target=self._loop, daemon=True).start()
        print(f"[*] CPA 智控维护引擎已启动 (周期: {CHECK_INTERVAL_MINUTES} 分钟)")

    def _loop(self):
        while self.is_running:
            try:
                self.run_maintenance()
            except Exception as e:
                print(f"[!] 运维守护线程异常: {e}")
            time.sleep(CHECK_INTERVAL_MINUTES * 60)

    def run_maintenance(self):
        """核心巡检流水线：洗牌(测活) -> 物理清理 -> 盘点水位 -> 解析补货"""
        if RUN_MODE != 1: return
        print(f"\n[Maintenance] >>> 启动全量仓库巡检流水线 <<<")
        
        # --- 场景 A: 同机部署/目录感知模式 (CPA_UPLOAD_ENABLED=0) ---
        if not CPA_UPLOAD_ENABLED:
            try:
                os.makedirs(TOKEN_OUTPUT_DIR, exist_ok=True)
                local_files = [f for f in os.listdir(TOKEN_OUTPUT_DIR) if f.endswith(".json")]
                
                print(f"[*] 阶段 1/3: 正在对本地 {len(local_files)} 个凭据执行真机测活...")
                
                # 并发洗牌测活
                from concurrent.futures import ThreadPoolExecutor
                active_count = 0
                with ThreadPoolExecutor(max_workers=5) as executor:
                    results = list(executor.map(self._test_local_file, local_files))
                    active_count = sum(1 for r in results if r is True)
                
                dead_count = len(local_files) - active_count
                print(f"[+] 阶段 2/3: 测活完毕。库存有效: {active_count}, 淘汰死号: {dead_count}")
                
                # 判定水位
                if active_count < MIN_ACCOUNTS_THRESHOLD:
                    diff = MIN_ACCOUNTS_THRESHOLD - active_count
                    print(f"[!] 水位告急: 有效库存仅剩 {active_count} 张 (阈值: {MIN_ACCOUNTS_THRESHOLD})，启动补货任务: +{diff} 个")
                    self.replenish_stock(diff)
                else:
                    print(f"[*] 阶段 3/3: 库存健康度良好 ({active_count}/{MIN_ACCOUNTS_THRESHOLD})，无需维护。")
                return 
            except Exception as e:
                print(f"[!] 本地巡检逻辑执行异常: {e}")
                return

        # --- 场景 B: 分布式/CPA API 智控模式 ---
        accounts = self.cpa.list_accounts()
        if not accounts: 
            print("[Maintenance] 仓库为空或 API 连接失败，准备初始化补货...")
            valid_count = 0
        else:
            print(f"[*] 阶段 1/4: 正在通过 API 深度测活 {len(accounts)} 个账号...")
            valid_count = 0
            for item in accounts:
                name = item.get("name")
                is_disabled = item.get("disabled", False)
                ok, msg = self.cpa.test_health(item.get("auth_index"), item.get("account_id"))
                
                if ok:
                    valid_count += 1
                    if is_disabled:
                        print(f"[+] {name} [已恢复]: 解除禁用。")
                        self.cpa.set_status(name, False)
                else:
                    if msg == "Overlimit":
                        if not is_disabled:
                            print(f"[-] {name} [限流]: 暂时禁用。")
                            self.cpa.set_status(name, True)
                    else:
                        print(f"[!] {name} [失效]: {msg}。正在执行物理删除...")
                        if self.cpa.delete_account(name):
                            print(f"[CLEAN] {name} 已从仓库彻底移除。")
                        else:
                            self.cpa.set_status(name, True)

        print(f"\n[*] 阶段 3/4: 水位对比。API 总活号: {valid_count} / 水位: {MIN_ACCOUNTS_THRESHOLD}")
        
        if valid_count < MIN_ACCOUNTS_THRESHOLD:
            needed = MIN_ACCOUNTS_THRESHOLD - valid_count
            print(f"[*] 阶段 4/4: 发起补货任务: +{needed}")
            threading.Thread(target=self.replenish_stock, args=(needed,), daemon=True).start()
        else:
            print(f"[*] 阶段 4/4: 水位充裕，巡检完成。")

    def _test_local_file(self, filename: str) -> bool:
        """对本地 credentials 下的 JSON 文件进行真机全息模拟测活"""
        path = os.path.join(TOKEN_OUTPUT_DIR, filename)
        email_prefix = filename.replace("token_", "").split("_")[0]
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            token = data.get("access_token") or data.get("token")
            if not token:
                print(f"[!] {filename} [RAW]: 格式非法，不含 Token。")
                return False
            
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
            
            # 探测：向 OpenAI 发起一次真实请求
            try:
                r = requests.get("https://chatgpt.com/backend-api/wham/usage", headers=headers, impersonate="chrome110", verify=_ssl_verify(), timeout=20)
                
                if r.status_code == 200:
                    print(f"[+] {email_prefix} [OK]: 账号存活。")
                    return True
                
                if r.status_code == 401:
                    print(f"[-] {email_prefix} [DEAD]: 凭据已失效 (401)。")
                    if CPA_CLEAN_DEAD:
                        try: os.remove(path)
                        except: pass
                    return False
                
                print(f"[?] {email_prefix} [WARN]: 接口响应异常 ({r.status_code})。")
                return False
            except Exception as e:
                print(f"[!] {email_prefix} [ERR]: 网络校验超时或拦截: {str(e)[:50]}")
                return False
        except Exception as e:
            print(f"[!] {filename} [FILE]: 文件读取失败: {e}")
            return False

    def replenish_stock(self, count: int):
        from concurrent.futures import ThreadPoolExecutor
        success_lock = threading.Lock()
        state = {"success_count": 0}

        def _job():
            while True:
                with success_lock:
                    if state["success_count"] >= count:
                        break
                
                try:
                    status, email, pwd = run_full_flow(PROXY)
                    if status and status.startswith("{"):
                        if process_registration_result(status, email, pwd, upload=True):
                            with success_lock:
                                state["success_count"] += 1
                                print(f"[Replenish] 补货进度: {state['success_count']}/{count} (成功: {email})")
                    
                    if email:
                        threading.Thread(target=delete_alias_emails, args=(email,), daemon=True).start()
                except Exception as e:
                    print(f"[Replenish] 补货线程执行异常: {e}")
                
                # 再次检查是否已满额
                with success_lock:
                    if state["success_count"] >= count:
                        break
                time.sleep(random.randint(3, 7))

        print(f"[*] 启动补货队列：目标成功 {count} 个，并发线程 {THREAD_COUNT}...")
        with ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
            for _ in range(THREAD_COUNT):
                executor.submit(_job)


def process_registration_result(status: str, email: str, pwd: str, upload: bool = True) -> bool:
    """统一处理注册结果：保存本地文件、追加列表、上传 CPA"""
    if not status.startswith("{"): return False
    try:
        os.makedirs(TOKEN_OUTPUT_DIR, exist_ok=True)
        # 统一命名规则：token_账户名_时间戳.json (解决文件重复问题)
        clean_name = email.replace("@", "_").replace(".", "_")
        ts = int(time.time())
        file_name = os.path.join(TOKEN_OUTPUT_DIR, f"token_{clean_name}_{ts}.json")
        
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(status)
        print(f"[+] ✅ 凭据已保存: {os.path.basename(file_name)}", flush=True)
        
        # 追加 accounts.txt
        accounts_path = os.path.join(SCRIPT_DIR, "accounts.txt")
        _append_line(accounts_path, f"{email}----{pwd}")
        print(f"[+] ✅ 账号已追加: accounts.txt", flush=True)
        
        # 仅在全局开启 CPA 上传且 upload 参数为 True 时尝试上传
        cpa_up_enabled = os.getenv("CPA_UPLOAD_ENABLED", "0") == "1"
        if upload and cpa_up_enabled:
            threading.Thread(target=upload_to_cpa, args=(email, pwd, status), daemon=True).start()
        elif RUN_MODE == 1 and not cpa_up_enabled:
            print(f"[*] (VPS模式/已断连) CPA 上传开关已关闭，仅本地存根。", flush=True)
        return True
    except Exception as e:
        print(f"[-] 处理注册结果异常: {e}", flush=True)
        return False

maintenance_task = MaintenanceTask()

# ==========================================
# 2. 验证码与底层网络工具
# ==========================================

def _extract_mail_content(mail_data: Dict[str, Any]) -> str:
    subject = str(mail_data.get("subject") or "")
    intro = str(mail_data.get("intro") or "")
    text = str(mail_data.get("text") or "")
    html = mail_data.get("html") or ""
    raw = str(mail_data.get("raw") or "")
    if isinstance(html, list): html = "\n".join(str(x) for x in html)
    
    combined = "\n".join([subject, intro, text, str(html), raw])
    try:
        combined = quopri.decodestring(combined.encode('utf-8')).decode('utf-8', errors='ignore')
    except Exception: pass
    return combined

def _extract_otp_code(content: str) -> str:
    if not content: return ""
    patterns = [
        r"(?i)Your ChatGPT code is\s*(\d{6})",
        r"(?i)verification code to continue:\s*(\d{6})",
        r"(?i)verification code[:\s\r\n]*(\d{6})",
        r"(?i)code is[:\s\r\n]*(\d{6})",
        r"Subject:.*?\b(\d{6})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if match: return match.group(1)
    fallback = re.search(r"(?<![a-zA-Z0-9])(\d{6})(?![a-zA-Z0-9])", content)
    return fallback.group(1) if fallback else ""

def _wait_for_imap_code(target_email: str, proxies: Any = None, max_retries: int = 20) -> str:
    """通过 IMAP 登录收件主账号并提取发送给裂变别名的验证码"""
    if not IMAP_USER or not IMAP_PASS:
        print("[-] 错误: IMAP_USER 或 IMAP_PASS 未配置")
        return ""

    # 如果没有指定服务器，默认根据域名判断
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    if "@outlook.com" in IMAP_USER.lower() or "@hotmail.com" in IMAP_USER.lower():
        imap_server = "outlook.office365.com"
        
    imap_port = 993
    processed_ids = set()
    
    print(f"[*] 正在登录中心收件箱 ({IMAP_USER})...")
    
    try:
        # 尝试注入代理（针对中国大陆网络）
        if proxies and "http" in proxies:
            try:
                import socks
                import socket
                parsed = urlparse(proxies["http"])
                proxy_host = parsed.hostname
                proxy_port = parsed.port or 80
                proxy_type = socks.HTTP if parsed.scheme.lower() in ['http', 'https'] else socks.SOCKS5
                
                # 临时替换全局 socket 拨号
                original_socket = socket.socket
                socks.set_default_proxy(proxy_type, proxy_host, proxy_port)
                socket.socket = socks.socksocket
                mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=20)
                socket.socket = original_socket
            except Exception as e:
                print(f"[!] IMAP 代理注入失败，尝试直连: {e}")
                mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=20)
        else:
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=20)

        mail.login(IMAP_USER, IMAP_PASS.replace(" ", ""))
    except Exception as e:
        print(f"[-] IMAP 登录失败: {e}")
        return ""

    print(f"[*] 等待验证码 (目标别名: {target_email})...")
    
    for attempt in range(max_retries):
        try:
            # 1. 优先扫描 INBOX 和 Spam
            folders = ['INBOX', '"[Gmail]/Spam"', 'Spam', '"[Gmail]/All Mail"']
            found_code = ""
            search_date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
            
            for folder in folders:
                try:
                    res, _ = mail.select(folder, readonly=False)
                    if res != 'OK': continue
                    
                    status, messages = mail.search(None, f'(FROM "openai.com" SINCE {search_date} UNSEEN)')
                    if status != 'OK' or not messages[0]:
                        status, messages = mail.search(None, f'(FROM "openai.com" SINCE {search_date})')

                    if status != 'OK' or not messages[0]: continue
                        
                    ids = messages[0].split()
                    print(f"[*] 文件夹 [{folder.strip('\"')}] 扫描中... (发现 {len(ids)} 封 OpenAI 邮件)")
                    
                    for i, mail_id in enumerate(reversed(ids)):
                        if mail_id in processed_ids: continue
                        
                        # 仅在处理较多邮件时显示每步进度
                        if len(ids) > 5 and i % 5 == 0:
                            print(f"    - 正在核对第 {i+1}/{len(ids)} 封...", end="\r")

                        res, msg_data = mail.fetch(mail_id, '(RFC822)')
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = email_lib.message_from_bytes(response_part[1])
                                h_to = str(msg.get("To", "")).lower()
                                h_delto = str(msg.get("Delivered-To", "")).lower()
                                target = target_email.lower()
                                
                                # 优先匹配头部 (快)
                                is_match = (target in h_to or target in h_delto)
                                
                                # 如果头部没匹配到，再尝试深度正文匹配 (慢)
                                if not is_match:
                                    try:
                                        if target in response_part[1].decode('utf-8', 'ignore').lower():
                                            is_match = True
                                    except: pass
                                
                                if is_match:
                                    code = _extract_otp_code(str(msg))
                                    if code:
                                        found_code = code
                                        mail.store(mail_id, '+FLAGS', '\\Seen')
                                        processed_ids.add(mail_id)
                                        print(f"\n[+] 匹配成功：验证码已提取！")
                                        break
                        if found_code: break
                except: continue
                if found_code: break
            
            if found_code:
                print(f"[+] 验证码提取成功: {found_code}")
                mail.logout()
                return found_code
        except Exception as e:
            print(f"[!] IMAP 异常: {e}")
        
        print(".", end="", flush=True)
        time.sleep(1)
        
    print("[-] 验证码提取超时。")
    try: mail.logout()
    except: pass
    return ""

def _get_imap_connection(server: str, port: int = 993):
    """通用的带代理支持的 IMAP 连接获取器"""
    try:
        # 本地模式或开启代理时尝试注入
        if PROXY and "http" in PROXY:
            import socks
            import socket
            parsed = urlparse(PROXY)
            proxy_host = parsed.hostname
            proxy_port = parsed.port or 80
            proxy_type = socks.HTTP if parsed.scheme.lower() in ['http', 'https'] else socks.SOCKS5
            
            original_socket = socket.socket
            socks.set_default_proxy(proxy_type, proxy_host, proxy_port)
            socket.socket = socks.socksocket
            mail = imaplib.IMAP4_SSL(server, port, timeout=25)
            socket.socket = original_socket
            return mail
    except Exception as e:
        log_reg(f"[!] IMAP 代理注入失败，尝试直连: {e}")
    
    return imaplib.IMAP4_SSL(server, port, timeout=25)

def delete_alias_emails(email_alias: str):
    """【彻底删除】物理级清理方案：支持代理直通、多文件夹适配与全语言回收站"""
    if not IMAP_USER or not IMAP_PASS: return 

    try:
        imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
        if "@outlook.com" in IMAP_USER.lower() or "@hotmail.com" in IMAP_USER.lower():
            imap_server = "outlook.office365.com"
            
        mail = _get_imap_connection(imap_server)
        mail.login(IMAP_USER, IMAP_PASS) # 不再移除空格，保持原始凭据
        
        folders = ['INBOX', '"[Gmail]/Spam"', 'Spam', '"[Gmail]/All Mail"', 'Sent']
        trash_names = [
            '"[Gmail]/Trash"', '"[Gmail]/Bin"', '"[Gmail]/Recycle Bin"', 
            '"[Gmail]/已删除邮件"', '"[Gmail]/垃圾箱"', 'Trash', 'Deleted Items'
        ]
        
        found_any = False
        target_email = email_alias.lower()

        for folder in folders:
            try:
                stat, _ = mail.select(folder, readonly=False)
                if stat != 'OK': continue
                
                # 采用最稳健的搜索方式：搜所有 OpenAI 邮件，然后本地过滤 To
                status, messages = mail.search(None, '(FROM "openai.com")')
                if status != "OK" or not messages[0]: continue
                
                msg_ids = messages[0].split()
                for msg_id in reversed(msg_ids):
                    res, msg_data = mail.fetch(msg_id, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg_obj = email_lib.message_from_bytes(response_part[1])
                            h_to = str(msg_obj.get("To", "")).lower()
                            h_delto = str(msg_obj.get("Delivered-To", "")).lower()
                            
                            if target_email in h_to or target_email in h_delto:
                                mail.store(msg_id, '+FLAGS', '\\Deleted')
                                for trash in trash_names:
                                    try:
                                        if mail.copy(msg_id, trash)[0] == 'OK': break
                                    except: continue
                                found_any = True
                mail.expunge()
            except: continue
        
        mail.logout()
    except Exception as e:
        if "login" in str(e).lower():
            log_reg(f"[!] 清理任务登录失败(IMAP): {e}")

def deep_clean_mailbox():
    """【深度全局清理】清除整个收件箱中所有来自 OpenAI 的残留邮件 (支持代理)"""
    if not IMAP_USER or not IMAP_PASS:
        log_reg("[-] 未配置 IMAP 账号，清除任务中止。")
        return

    log_reg("[*] 正在启动全局清理引擎 (尝试建立加密连接)...")
    try:
        imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
        if "@outlook.com" in IMAP_USER.lower() or "@hotmail.com" in IMAP_USER.lower():
            imap_server = "outlook.office365.com"
            
        mail = _get_imap_connection(imap_server)
        mail.login(IMAP_USER, IMAP_PASS)
        
        folders = ['INBOX', '"[Gmail]/Spam"', 'Spam', '"[Gmail]/All Mail"', 'Sent']
        trash_names = ['"[Gmail]/Trash"', '"[Gmail]/Bin"', 'Trash', 'Deleted Items']
        
        total_found = 0
        for folder in folders:
            try:
                stat, _ = mail.select(folder, readonly=False)
                if stat != 'OK': continue
                
                status, messages = mail.search(None, '(FROM "openai.com")')
                if status != "OK" or not messages[0]: continue
                
                ids = messages[0].split()
                for mid in ids:
                    mail.store(mid, '+FLAGS', '\\Deleted')
                    for trash in trash_names:
                        try:
                            if mail.copy(mid, trash)[0] == 'OK': break
                        except: continue
                    total_found += 1
                mail.expunge()
            except: continue
            
        if total_found > 0:
            log_reg(f"[+] 🧹 清理大获全胜：共抹除 {total_found} 封残留邮件。")
        else:
            log_reg("[*] 邮箱非常整洁，未发现残留邮件。")
        mail.logout()
    except Exception as e:
        log_reg(f"[-] 全局清理失败: {e}")

# (Worker 模式已移除, 统一使用 IMAP 进行主账号验证)

def _post_with_retry(session: requests.Session, url: str, *, headers: Dict[str, Any], data: Any = None, json_body: Any = None, proxies: Any = None, timeout: int = 30, retries: int = 2, allow_redirects: bool = True) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            if json_body is not None: return session.post(url, headers=headers, json=json_body, proxies=proxies, verify=_ssl_verify(), timeout=timeout, allow_redirects=allow_redirects)
            return session.post(url, headers=headers, data=data, proxies=proxies, verify=_ssl_verify(), timeout=timeout, allow_redirects=allow_redirects)
        except Exception as e:
            last_error = e
            if attempt >= retries: break
            time.sleep(2 * (attempt + 1))
    if last_error: raise last_error

def _session_post_retry(session, url, **kwargs):
    """专门针对 curl_cffi 会话的带重试 POST 请求封装"""
    retries = kwargs.pop("retries", 3)
    last_err = None
    for i in range(retries):
        try:
            return session.post(url, **kwargs)
        except Exception as e:
            last_err = e
            if i < retries - 1:
                print(f"[*] 网络波动，正在进行第 {i+1} 次重试...")
                time.sleep(random.uniform(1.5, 3.5))
                continue
            raise last_err


def _follow_redirect_chain(session: requests.Session, start_url: str, proxies: Optional[Dict[str, str]], max_redirects: int = 12) -> Tuple[Optional[Any], str]:
    current_url = start_url
    response = None
    for _ in range(max_redirects):
        try:
            response = session.get(current_url, allow_redirects=False, proxies=proxies, verify=_ssl_verify(), timeout=30)
        except Exception as e:
            print(f"[-] 🚫 请求重定向阶段出现网络异常: {e}")
            return None, current_url
        if response.status_code not in [301, 302, 303, 307, 308]: return response, current_url
        location = response.headers.get("Location", "")
        if not location: return response, current_url
        current_url = urljoin(current_url, location)
        if "code=" in current_url and "state=" in current_url: return None, current_url
    return response, current_url

def _build_sentinel_header(session: requests.Session, flow: str, proxies: Optional[Dict[str, str]]) -> Optional[str]:
    did = session.cookies.get("oai-did")
    if not did: return None
    try:
        sentinel_resp = requests.post(
            "https://sentinel.openai.com/backend-api/sentinel/req",
            headers={"Origin": "https://sentinel.openai.com", "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html?sv=20260219f9f6", "Content-Type": "text/plain;charset=UTF-8"},
            data=json.dumps({"p": "", "id": did, "flow": flow}), proxies=proxies, impersonate="chrome110", verify=_ssl_verify(), timeout=30
        )
        if sentinel_resp.status_code != 200: return None
        token = str((sentinel_resp.json() or {}).get("token") or "").strip()
        if not token: return None
        return json.dumps({"p": "", "t": "", "c": token, "id": did, "flow": flow}, ensure_ascii=False, separators=(",", ":"))
    except Exception: return None

def _decode_jwt_segment(seg: str) -> Dict[str, Any]:
    try:
        padding = "=" * (-len(seg) % 4)
        raw = base64.urlsafe_b64decode((seg + padding).encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception: return {}

def _extract_next_url(data: Dict[str, Any]) -> str:
    continue_url = str(data.get("continue_url") or "").strip()
    if continue_url: return continue_url
    page_type = str((data.get("page") or {}).get("type") or "").strip()
    mapping = {"email_otp_verification": "https://auth.openai.com/email-verification", "sign_in_with_chatgpt_codex_consent": "https://auth.openai.com/sign-in-with-chatgpt/codex/consent", "workspace": "https://auth.openai.com/workspace"}
    return mapping.get(page_type, "")

# ==========================================
# 3. 随机资料生成
# ==========================================

FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
    "Emma", "Olivia", "Ava", "Isabella", "Sophia", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn"
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"
]

def generate_random_user_info() -> dict:
    """生成随机用户信息 (补全名+姓与年龄范围)"""
    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    current_year = datetime.now().year
    birth_year = random.randint(current_year - 25, current_year - 18)
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)
    return {"name": name, "birthdate": f"{birth_year}-{birth_month:02d}-{birth_day:02d}"}

# ==========================================
# 4. Token 解析保存与交换
# ==========================================

def submit_callback_url(callback_url: str, code_verifier: str, redirect_uri: str, expected_state: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        parsed = urlparse(callback_url)
        params = parse_qs(parsed.query)
        if "error" in params or "code" not in params or "state" not in params: return None
        if params["state"][0] != expected_state: return None

        token_resp = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            data=urlencode({"grant_type": "authorization_code", "code": params["code"][0], "redirect_uri": redirect_uri, "client_id": "app_EMoamEEZ73f0CkXaXp7hrann", "code_verifier": code_verifier}),
            impersonate="chrome110", proxies=proxies, verify=_ssl_verify(), timeout=30
        )
        if token_resp.status_code != 200: return None
        
        token_data = token_resp.json()
        id_token = str(token_data.get("id_token") or "").strip()
        claims = _decode_jwt_segment(id_token.split(".")[1]) if "." in id_token else {}
        
        now_local = datetime.now().astimezone()
        expired_local = now_local + timedelta(seconds=max(int(token_data.get("expires_in") or 0), 0))
        
        return {
            "access_token": str(token_data.get("access_token") or "").strip(),
            "account_id": str((claims.get("https://api.openai.com/auth") or {}).get("chatgpt_account_id") or "").strip(),
            "disabled": False,
            "email": str(claims.get("email") or "").strip(),
            "expired": expired_local.isoformat(timespec="seconds"),
            "id_token": id_token,
            "last_refresh": now_local.isoformat(timespec="seconds"),
            "refresh_token": str(token_data.get("refresh_token") or "").strip(),
            "type": "codex",
        }
    except Exception: return None

def _generate_password(length: int = 16) -> str:
    chars = random.choices(string.ascii_uppercase, k=2) + random.choices(string.ascii_lowercase, k=2) + random.choices(string.digits, k=2) + random.choices("!@#$%&*", k=2) + random.choices(string.ascii_letters + string.digits + "!@#$%&*", k=length - 8)
    random.shuffle(chars)
    return "".join(chars)

# ==========================================
# 4. 核心流程：註冊與降級登入
# ==========================================

def run_full_flow(proxy: Optional[str]) -> tuple:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    password = _generate_password()
    
    # 顺序轮转选取主邮箱 (不再随机)
    master_obj = _pick_next_master()
    if not master_obj:
        print("[-] ❌ 错误: 所有主邮箱均在冷却期或列表为空！")
        return "fail_no_master", "", ""
    master_email = master_obj["email"]
    
    email = _generate_fission_email(master_email, GMAIL_TAG_LEN)
    print(f"[*] 轮转选中主邮箱: {master_email} (系统自动执行最优裂变模式)")

    print(f"[*] 生成的密碼: [已保存]")
    
    saved_mail_id = "" # 用來記住第一封郵件的 ID

    # ------------------
    # 第一階段：註冊
    # ------------------
    print(f"[*] 初始化 OAuth 註冊流程...")
    s_reg = requests.Session(proxies=proxies, impersonate="chrome110")
    # 移除手动 User-Agent 覆盖，让 curl_cffi 自行匹配指纹
    # s_reg.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})

    oauth_reg = OAuthConfiguration()
    _, challenge_reg = oauth_reg.generate_pkad_params()
    oauth_reg.state = secrets.token_urlsafe(32)
    reg_url = f"{AUTH_URL}?response_type=code&client_id={oauth_reg.client_id}&redirect_uri={quote(oauth_reg.redirect_uri, safe='')}&scope={quote(oauth_reg.scope, safe='')}&state={oauth_reg.state}&code_challenge={challenge_reg}&code_challenge_method=S256&prompt=login&id_token_add_organizations=true&codex_cli_simplified_flow=true"
    
    try:
        res = s_reg.get(reg_url, proxies=proxies, verify=_ssl_verify(), timeout=30)
        if res.status_code != 200:
            print(f"[*] 初始请求状态码: {res.status_code} ❌")
            if "unsupported_country" in res.text:
                print("[-] ❌ 错误：当前代理 IP 所在的国家/地区不被 OpenAI 支持！(如：香港、俄罗斯等)")
                print("[*] 请立即在您的代理软件中切换到其他区域节点 (如：美国、日本、新加坡等)")
                return "fail_geo_blocked", email, password
    except Exception as e:
        print(f"[-] 🚫 连接 OpenAI 失败: {e}")
        # 如果报错包含超时且是直连，尝试打印一些环境信息
        if "timed out" in str(e).lower() and not proxies:
            print("[!] 诊断建议: 您的浏览器可访问但程序超时，这通常是由于 DNS 污染或 TLS 握手被拦截。")
            print("[!] 建议: 检查是否有系统全局代理，或尝试将系统 DNS 设置为 8.8.8.8")
        return "fail_connect", email, password

    did = s_reg.cookies.get("oai-did")
    if not did:
        print(f"[!] 警告: 未能获取到 Device ID (oai-did)。响应内容片段: {res.text[:200]}")
    else:
        print(f"[*] Device ID: {did}")
    time.sleep(0.1)
    
    st_reg = _build_sentinel_header(s_reg, "authorize_continue", proxies)
    if not st_reg: 
        print("[-] ❌ OpenAI 反欺诈墙 (Sentinel) 拒绝了该 IP。当前节点 IP 质量查或被标记。")
        return "fail_sentinel_blocked", email, password
    
    print(f"[*] 提交 Email: {email}")
    signup_resp = s_reg.post("https://auth.openai.com/api/accounts/authorize/continue", headers={"referer": "https://auth.openai.com/create-account", "accept": "application/json", "content-type": "application/json", "openai-sentinel-token": st_reg}, data=json.dumps({"username": {"value": email, "kind": "email"}, "screen_hint": "signup"}), proxies=proxies, verify=_ssl_verify())
    
    if signup_resp.status_code == 403 or str(signup_resp.status_code).startswith("40"):
        print(f"[-] ❌ OpenAI 注册被拒: HTTP {signup_resp.status_code} (触发主邮箱冷却模式)")
        blacklist_mgr.put_in_jail(master_email, COOL_DOWN_HOURS)
        return "retry_40x", email, password
    elif signup_resp.status_code == 429:
        print(f"[-] ❌ 请求过于频繁: HTTP 429 (请更换节点或稍后再试)")
        return "retry_429", email, password
    elif signup_resp.status_code != 200:
        print(f"[-] ❌ 注册过程异常: HTTP {signup_resp.status_code}")
        
    print(f"[*] Signup 表單状态: {signup_resp.status_code} {'✅' if signup_resp.status_code==200 else '❌'}")
    
    print(f"[*] 提交密碼...")
    pwd_resp = s_reg.post("https://auth.openai.com/api/accounts/user/register", headers={"referer": "https://auth.openai.com/create-account/password", "accept": "application/json", "content-type": "application/json", "openai-sentinel-token": st_reg}, data=json.dumps({"password": password, "username": email}), proxies=proxies, verify=_ssl_verify())
    print(f"[*] 密碼提交狀態: {pwd_resp.status_code} {'✅' if pwd_resp.status_code==200 else '❌'}")
    reg_json = pwd_resp.json() if pwd_resp.status_code == 200 else {}
    register_continue = reg_json.get("continue_url", "")
    
    need_otp = "email-verification" in register_continue or "verify" in register_continue
    if not need_otp: need_otp = "verification" in str(reg_json) or "otp" in str(reg_json)

    if need_otp:
        print(f"[*] 發送 OTP...")
        if register_continue:
            otp_send_url = register_continue if register_continue.startswith("http") else f"https://auth.openai.com{register_continue}"
            send_resp = _post_with_retry(s_reg, otp_send_url, headers={"referer": "https://auth.openai.com/create-account/password", "accept": "application/json", "content-type": "application/json", "openai-sentinel-token": st_reg}, json_body={}, proxies=proxies)
            print(f"[*] OTP 發送狀態: {send_resp.status_code} {'✅' if send_resp.status_code==200 else '❌'}")
            
        # 统一使用 IMAP 抓取代码
        code_reg = _wait_for_imap_code(email, proxies, max_retries=15)
        
        if not code_reg: return "fail_otp", email, password
        
        print(f"[*] 驗證 OTP: {code_reg}")
        val_resp = _post_with_retry(s_reg, "https://auth.openai.com/api/accounts/email-otp/validate", headers={"referer": "https://auth.openai.com/email-verification", "accept": "application/json", "content-type": "application/json", "openai-sentinel-token": st_reg}, json_body={"code": code_reg}, proxies=proxies)
        print(f"[*] OTP 驗證狀態: {val_resp.status_code} {'✅' if val_resp.status_code==200 else '❌'}")
        try: register_continue = val_resp.json().get("continue_url") or register_continue
        except: pass

    time.sleep(0.1)
    if register_continue:
        state_url = register_continue if register_continue.startswith("http") else f"https://auth.openai.com{register_continue}"
        s_reg.get(state_url, proxies=proxies, verify=_ssl_verify(), timeout=30)
        time.sleep(0.1)

    print(f"[*] 創建帳號...")
    user_info = generate_random_user_info()
    print(f"[*] 使用随机资料: {user_info['name']} ({user_info['birthdate']})")
    create_resp = _post_with_retry(s_reg, "https://auth.openai.com/api/accounts/create_account", headers={"referer": "https://auth.openai.com/about-you", "accept": "application/json", "content-type": "application/json"}, data=json.dumps(user_info), proxies=proxies, allow_redirects=False)
    print(f"[*] 帳號創建狀態: {create_resp.status_code}")
    
    auth_cookie = s_reg.cookies.get("oai-client-auth-session")
    has_workspace = False
    if auth_cookie and "." in auth_cookie:
        claims = _decode_jwt_segment(auth_cookie.split(".")[1])
        workspaces = claims.get("workspaces") or []
        if workspaces: has_workspace = True
    
    if not has_workspace:
        print(f"[*] === 登入流程 ===")
        
        # ------------------
        # 第二階段：降級登入
        # ------------------
        email_id = email.split("@")[0][:14]
        print(f"[*] 初始化 OAuth 登入流程...")
        
        s_log = requests.Session(proxies=proxies, impersonate="chrome110")
        s_log.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})

        oauth_log = OAuthConfiguration()
        _, challenge_log = oauth_log.generate_pkad_params()
        oauth_log.state = secrets.token_urlsafe(32)
        log_url = f"{AUTH_URL}?response_type=code&client_id={oauth_log.client_id}&redirect_uri={quote(oauth_log.redirect_uri, safe='')}&scope={quote(oauth_log.scope, safe='')}&state={oauth_log.state}&code_challenge={challenge_log}&code_challenge_method=S256&prompt=login&id_token_add_organizations=true&codex_cli_simplified_flow=true"

        resp, current_url = _follow_redirect_chain(s_log, log_url, proxies)
        if "code=" in current_url and "state=" in current_url:
            token_json = submit_callback_url(current_url, oauth_log.code_verifier, oauth_log.redirect_uri, oauth_log.state, proxy)
            if token_json: return json.dumps(token_json, ensure_ascii=False, indent=2), email, password

        st_log = _build_sentinel_header(s_log, "authorize_continue", proxies)
        login_start_resp = _session_post_retry(s_log, "https://auth.openai.com/api/accounts/authorize/continue", headers={"Content-Type": "application/json", "Accept": "application/json", "Referer": current_url, "OpenAI-Sentinel-Token": st_log or ""}, data=json.dumps({"username": {"value": email, "kind": "email"}}), proxies=proxies, verify=_ssl_verify(), timeout=35)
        
        if login_start_resp.status_code != 200: return "fail_login", email, password
        password_page_url = str(login_start_resp.json().get("continue_url") or "").strip()
        resp, current_url = _follow_redirect_chain(s_log, password_page_url, proxies)

        print(f"[*] 驗證密碼...")
        st_pwd = _build_sentinel_header(s_log, "password_verify", proxies)
        password_resp = _session_post_retry(s_log, "https://auth.openai.com/api/accounts/password/verify", headers={"Content-Type": "application/json", "Accept": "application/json", "Referer": current_url, "OpenAI-Sentinel-Token": st_pwd or ""}, data=json.dumps({"password": password}), proxies=proxies, verify=_ssl_verify(), timeout=35)
        if password_resp.status_code != 200: return "fail_pwd", email, password

        next_url = _extract_next_url(password_resp.json())
        resp, current_url = _follow_redirect_chain(s_log, next_url, proxies)
        
        if current_url.endswith("/email-verification"):
            print(f"[*] 需要 Email OTP 驗證...")
            login_code = _wait_for_imap_code(email, proxies, max_retries=15)
            
            if not login_code: return "fail_login_otp", email, password
            
            # 使用带重试的 POST 逻辑解决超时问题
            otp_resp = _session_post_retry(s_log, "https://auth.openai.com/api/accounts/email-otp/validate", headers={"Content-Type": "application/json", "Accept": "application/json", "Referer": current_url}, data=json.dumps({"code": login_code}), proxies=proxies, verify=_ssl_verify(), timeout=35)
            next_url = _extract_next_url(otp_resp.json())
            resp, current_url = _follow_redirect_chain(s_log, next_url, proxies)
            
        if "code=" in current_url and "state=" in current_url:
            token_json = submit_callback_url(current_url, oauth_log.code_verifier, oauth_log.redirect_uri, oauth_log.state, proxy)
            if token_json: return json.dumps(token_json, ensure_ascii=False, indent=2), email, password

        if current_url.endswith("/sign-in-with-chatgpt/codex/consent") or current_url.endswith("/workspace"):
            print(f"[*] 需要 Workspace 授權...")
            auth_cookie2 = s_log.cookies.get("oai-client-auth-session")
            if auth_cookie2:
                workspaces = _decode_jwt_segment(auth_cookie2.split(".")[0]).get("workspaces") or []
                if workspaces:
                    select_resp = _session_post_retry(s_log, "https://auth.openai.com/api/accounts/workspace/select", headers={"Content-Type": "application/json", "Accept": "application/json", "Referer": current_url}, data=json.dumps({"workspace_id": str(workspaces[0].get("id"))}), proxies=proxies, verify=_ssl_verify(), timeout=35)
                    if select_resp.status_code == 200:
                        n_url = _extract_next_url(select_resp.json())
                        _, final_url = _follow_redirect_chain(s_log, n_url, proxies)
                        if "code=" in final_url and "state=" in final_url:
                            token_json = submit_callback_url(final_url, oauth_log.code_verifier, oauth_log.redirect_uri, oauth_log.state, proxy)
                            if token_json: return json.dumps(token_json, ensure_ascii=False, indent=2), email, password

        return "fail_downgrade", email, password
    else:
        print(f"[*] 註冊自帶 Workspace，交由主循環處理...")
        return "success_no_downgrade", email, password

# ==========================================
# 6. 主循环引擎（多线程 + 分区 UI）
# ==========================================

class RedirectText:
    """将 print 重定向到指定 Tkinter 文本框，支持线程安全"""
    def __init__(self, text_ctrl):
        self.output = text_ctrl
        self._lock = threading.Lock()

    def write(self, string):
        self.output.after(0, self._append, string)

    def _append(self, string):
        self.output.config(state=tk.NORMAL)
        self.output.insert(tk.END, string)
        self.output.see(tk.END)
        self.output.config(state=tk.DISABLED)

    def flush(self):
        pass


import builtins # 核心补全：使用底层打印逃离递归陷阱

# --- 全局日志系统 (兼容 VPS & GUI) ---
_GUI_INSTANCE = None

def log_reg(msg: str):
    """全局注册日志汇报：同步底层输出与 GUI (智能去重)"""
    msg = msg.strip()
    if not msg: return
    # 如果已经有前缀了，就不再加 [*]
    prefix = "" if (msg.startswith("[") and "]" in msg[:10]) else "[*] "
    full_msg = f"{prefix}{msg}"
    
    # VPS 模式下直接通过 builtins.print 输出到终端
    # GUI 模式下，由于 sys.stdout 已重定向到 RedirectText，builtins.print 会触发 RedirectText.write 从而自动插入到 reg_log
    # 唯一的问题是 log_reg 可能被想要显示在 reg_log 但不想在终端显示的逻辑调用，或者我们想精确控制插入
    
    if _GUI_INSTANCE:
        # GUI 模式下，直接调用 insert 以确保即时性，并避免触发 stdout 循环（虽然 builtins.print 应该安全）
        # 但为了防止双重输出（一个是 builtins.print 触发的，一个是手动 insert 的），我们只选其一
        def _do():
            try:
                _GUI_INSTANCE.reg_log.config(state=tk.NORMAL)
                _GUI_INSTANCE.reg_log.insert(tk.END, f"{full_msg}\n")
                _GUI_INSTANCE.reg_log.see(tk.END)
                _GUI_INSTANCE.reg_log.config(state=tk.DISABLED)
            except: pass
        _GUI_INSTANCE.root.after(0, _do)
    else:
        # 非 GUI 模式 (VPS) 直接打印
        builtins.print(full_msg, flush=True)

def log_cpa(msg: str):
    """全局 CPA 日志汇报：同步底层输出与 GUI (智能去重)"""
    msg = msg.strip()
    if not msg: return
    prefix = "" if (msg.startswith("[") and "]" in msg[:10]) else "[CPA] "
    full_msg = f"{prefix}{msg}"
    
    if _GUI_INSTANCE:
        def _do():
            try:
                _GUI_INSTANCE.cpa_log.config(state=tk.NORMAL)
                _GUI_INSTANCE.cpa_log.insert(tk.END, f"{full_msg}\n")
                _GUI_INSTANCE.cpa_log.see(tk.END)
                _GUI_INSTANCE.cpa_log.config(state=tk.DISABLED)
            except: pass
        _GUI_INSTANCE.root.after(0, _do)
    else:
        builtins.print(full_msg, flush=True)

class OpenApp:
    def __init__(self, root):
        global _GUI_INSTANCE
        _GUI_INSTANCE = self  # 注册全局句柄
        self.root = root
        self.root.title("OpenAI 自动注册与 Token 提取器 Pro v3.3")
        self.root.geometry("1200x700")
        self.root.configure(bg="#1A1A2E")

        self.running_event = threading.Event()
        self.worker_threads: list = []
        self.proxy = os.getenv("PROXY")
        self.thread_count = tk.IntVar(value=THREAD_COUNT)
        self.target_success_count = tk.IntVar(value=TARGET_SUCCESS_COUNT)

        # 线程安全统计
        self._lock = threading.Lock()
        self.success_count = 0
        self.fail_count = 0
        self.upload_threads: list = []

        # 今日数据（按日期累积）
        self._today_key = datetime.now().strftime("%Y-%m-%d")
        self._today_success = 0
        self._today_fail = 0

        # 自动下载图标
        icon_path = os.path.join(SCRIPT_DIR, "openai.ico")
        try:
            if not os.path.exists(icon_path):
                test_proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
                icon_res = requests.get("https://chatgpt.com/favicon.ico", proxies=test_proxies, impersonate="chrome110", timeout=10, verify=_ssl_verify())
                if icon_res.status_code == 200:
                    with open(icon_path, "wb") as f:
                        f.write(icon_res.content)
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self.sleep_min = 0
        self.sleep_max = 0
        self.setup_ui()
        
        # 启动 CPA 运维任务 (如果开启)
        if CPA_MAINTENANCE_ENABLED:
            maintenance_task.start()

    def setup_ui(self):
        # ---- 顶部控制栏 ----
        ctrl = tk.Frame(self.root, bg="#16213E", pady=6)
        ctrl.pack(fill=tk.X, side=tk.TOP)

        btn_style = {"relief": tk.FLAT, "font": ("Consolas", 10, "bold"), "pady": 4, "padx": 12, "cursor": "hand2"}

        self.start_btn = tk.Button(ctrl, text="▶  开始运行", bg="#0F3460", fg="#E5E5E5", activebackground="#1A5276", **btn_style, command=self.start_task)
        self.start_btn.pack(side=tk.LEFT, padx=(10, 4))

        self.stop_btn = tk.Button(ctrl, text="⏹  停止运行", bg="#6E2020", fg="#E5E5E5", activebackground="#922B21", **btn_style, command=self.stop_task, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=4)

        # 今日报告按钮
        self.report_btn = tk.Button(ctrl, text="📊  今日注册报告", bg="#145A32", fg="#E5E5E5", activebackground="#1E8449", **btn_style, command=self.show_report)
        self.report_btn.pack(side=tk.LEFT, padx=4)

        # 线程数设置
        tk.Label(ctrl, text="并发线程:", bg="#16213E", fg="#A0A0B0", font=("Consolas", 10)).pack(side=tk.LEFT, padx=(20, 4))

        self.thread_spin = tk.Spinbox(ctrl, from_=1, to=100, textvariable=self.thread_count, width=5, bg="#0F3460", fg="white", buttonbackground="#16213E", relief=tk.FLAT)
        self.thread_spin.pack(side=tk.LEFT, padx=4)

        tk.Label(ctrl, text="  目标成功数:", bg="#16213E", fg="#E5E5E5", font=("Arial", 9)).pack(side=tk.LEFT, padx=(10, 2))
        self.target_spin = tk.Spinbox(ctrl, from_=1, to=9999, textvariable=self.target_success_count, width=6, bg="#0F3460", fg="white", buttonbackground="#16213E", relief=tk.FLAT)
        self.target_spin.pack(side=tk.LEFT, padx=4)

        # 实时统计显示
        self.stat_label = tk.Label(ctrl, text="✓ 0  ✗ 0", bg="#16213E", fg="#58D68D", font=("Consolas", 10, "bold"))
        self.stat_label.pack(side=tk.LEFT, padx=(20, 4))
        
        # 编辑配置按钮
        self.edit_btn = tk.Button(ctrl, text="⚙️ 编辑配置", bg="#34495E", fg="#E5E5E5", activebackground="#2C3E50", **btn_style, command=self.edit_config)
        self.edit_btn.pack(side=tk.RIGHT, padx=10)

        # 手动巡检按钮 (仅在 VPS 模式显示)
        if RUN_MODE == 1 and CPA_MAINTENANCE_ENABLED:
            self.check_btn = tk.Button(ctrl, text="🔍 立即巡检仓库", bg="#512E5F", fg="#E5E5E5", activebackground="#4A235A", **btn_style, command=lambda: threading.Thread(target=maintenance_task.run_maintenance, daemon=True).start())
            self.check_btn.pack(side=tk.RIGHT, padx=4)

        # 手动清理邮件按钮
        self.clean_btn = tk.Button(ctrl, text="🧹 清理邮件", bg="#A04000", fg="#E5E5E5", activebackground="#BA4A00", **btn_style, command=lambda: threading.Thread(target=deep_clean_mailbox, daemon=True).start())
        self.clean_btn.pack(side=tk.RIGHT, padx=4)

        # 手动测试 CPA 连通性按钮 (放在清理邮件左边)
        self.test_cpa_btn = tk.Button(ctrl, text="🧪 测试 CPA", bg="#2874A6", fg="#E5E5E5", activebackground="#1B4F72", **btn_style, 
                                     command=lambda: threading.Thread(target=self._test_cpa_connection, daemon=True).start())
        self.test_cpa_btn.pack(side=tk.RIGHT, padx=4)

        # ---- 分区工作台 ----
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#1A1A2E", sashwidth=5, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 6))

        # 左侧：注册日志
        left_frame = tk.Frame(paned, bg="#1A1A2E")
        tk.Label(left_frame, text=" 🔄 注册工作台", bg="#0F3460", fg="#85C1E9",
                 font=("Consolas", 10, "bold"), anchor=tk.W).pack(fill=tk.X)
        self.reg_log = tk.Text(left_frame, wrap=tk.WORD, font=("Consolas", 9),
                                bg="#0D1117", fg="#C9D1D9", state=tk.DISABLED,
                                insertbackground="#C9D1D9", selectbackground="#264F78",
                                relief=tk.FLAT, bd=0)
        sb1 = ttk.Scrollbar(left_frame, command=self.reg_log.yview)
        self.reg_log.config(yscrollcommand=sb1.set)
        sb1.pack(side=tk.RIGHT, fill=tk.Y)
        self.reg_log.pack(fill=tk.BOTH, expand=True)
        paned.add(left_frame, minsize=400)

        # 右侧：CPA 上传日志
        right_frame = tk.Frame(paned, bg="#1A1A2E")
        tk.Label(right_frame, text=" ☁️  CPA 上传工作台", bg="#145A32", fg="#82E0AA",
                 font=("Consolas", 10, "bold"), anchor=tk.W).pack(fill=tk.X)
        self.cpa_log = tk.Text(right_frame, wrap=tk.WORD, font=("Consolas", 9),
                                bg="#0D1117", fg="#82E0AA", state=tk.DISABLED,
                                insertbackground="#82E0AA", selectbackground="#264F78",
                                relief=tk.FLAT, bd=0)
        sb2 = ttk.Scrollbar(right_frame, command=self.cpa_log.yview)
        self.cpa_log.config(yscrollcommand=sb2.set)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)
        self.cpa_log.pack(fill=tk.BOTH, expand=True)
        paned.add(right_frame, minsize=280)

        # 重定向：注册日志 → reg_log
        self._reg_redirector = RedirectText(self.reg_log)
        sys.stdout = self._reg_redirector
        sys.stderr = self._reg_redirector

        self._print_reg(f"[*] OpenAI 多线程 CPA 自动注册版 启动")
        self._print_reg(f"[*] 結果目錄: {os.path.abspath(TOKEN_OUTPUT_DIR)}")
        self._print_cpa("[*] CPA 上传工作台就绪，等待账号入库...")

        if self.proxy and "127.0.0.1" in self.proxy:
            if not _check_proxy_alive(self.proxy):
                self._print_reg(f"[!] 警告: 本地代理端口可能未开启 ({self.proxy})")

        self._print_reg("[*] 正在检测与 OpenAI 的网络连通性...")
        def _check_net():
            try:
                test_proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
                requests.get("https://auth.openai.com/favicon.ico", proxies=test_proxies, impersonate="chrome110", timeout=30, verify=_ssl_verify())
                self.root.after(0, lambda: self._print_reg("[+] 网络连通性测试通过。"))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._print_reg(f"[!] 连通性测试未通过 ({err_msg})"))
        threading.Thread(target=_check_net, daemon=True).start()

    def edit_config(self):
        """打开配置编辑向导并重新加载环境变量"""
        if self.running_event.is_set():
            messagebox.showwarning("警告", "请先停止当前运行的任务再修改配置！")
            return
            
        path = os.path.join(SCRIPT_DIR, ".env")
        if show_config_wizard(path, is_edit=True, parent=self.root):
            # 重新加载 .env 变量
            _load_dotenv(path)
            # 全量刷新全局变量和逻辑
            reload_all_configs()
            
            # 更新当前实例缓存
            self.proxy = os.getenv("PROXY")
            self._print_reg("[+] 配置已全量更新并重新同步到运行内存。")

    def _print_reg(self, msg: str):
        """兼容旧版代码：转发给全局 log_reg"""
        log_reg(msg)

    def _print_cpa(self, msg: str):
        """兼容旧版代码：转发给全局 log_cpa"""
        log_cpa(msg)

    def _update_stat(self):
        """更新统计数据到 GUI"""
        if hasattr(self, 'stat_label'):
            def _do():
                try: self.stat_label.config(text=f"✓ {self.success_count}  ✗ {self.fail_count}")
                except: pass
            self.root.after(0, _do)

    def _test_cpa_connection(self):
        """主界面发起 CPA 连通性测试"""
        self._print_cpa("[*] 正在从主界面发起连通性测试...")
        test_file = "ceshi.json"
        test_content = json.dumps({"test_interface": "main_gui", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        
        try:
            # 创建符合后端后缀校验的 .json 临时文件
            with open(test_file, "w", encoding="utf-8") as f: 
                f.write(test_content)
            
            # 执行全链路上传 (含自愈直连逻辑)
            success = upload_to_cpa("gui_test_node", "debug", test_content, custom_filename=test_file)
            
            if success:
                messagebox.showinfo("测试成功", "✅ CPA 接口连通性测试通过！\n测试文件已成功入库并清理。", parent=self.root)
            else:
                self._print_cpa("[-] 连通性测试失败，请检查 URL 或 WAF 防护。")
                messagebox.showerror("测试失败", "❌ 连通性测试未通过！\n请检查 CPA 配置或网络环境。", parent=self.root)
        except Exception as e:
            self._print_cpa(f"[-] 测试过程发生异常: {e}")
            messagebox.showerror("异常", f"测试过程发生错误: {e}", parent=self.root)
        finally:
            if os.path.exists(test_file): 
                try: os.remove(test_file)
                except: pass

    def show_report(self):
        """显示今日注册报告"""
        # 读取今日 token 文件数量
        today_str = datetime.now().strftime("%Y-%m-%d")
        token_dir = TOKEN_OUTPUT_DIR
        today_files = 0
        try:
            for f in os.listdir(token_dir):
                if f.endswith(".json"):
                    fpath = os.path.join(token_dir, f)
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d")
                    if mtime == today_str:
                        today_files += 1
        except Exception:
            pass

        total = self.success_count + self.fail_count
        rate = f"{self.success_count/total*100:.1f}%" if total > 0 else "N/A"

        win = tk.Toplevel(self.root)
        win.title("今日注册报告")
        win.geometry("380x280")
        win.configure(bg="#0D1117")
        win.resizable(False, False)

        tk.Label(win, text="📊  今日注册报告", bg="#0F3460", fg="#85C1E9",
                 font=("Consolas", 12, "bold"), pady=10).pack(fill=tk.X)

        rows = [
            ("📅 统计日期", today_str),
            ("🔁 本次会话总尝试", f"{total} 次"),
            ("✅ 注册成功", f"{self.success_count} 个"),
            ("❌ 注册失败", f"{self.fail_count} 个"),
            ("📈 成功率", rate),
            ("💾 今日 Token 文件", f"{today_files} 个"),
            ("🧵 并发线程数", f"{self.thread_count.get()} 线程"),
        ]

        frame = tk.Frame(win, bg="#0D1117", pady=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=20)

        for label, value in rows:
            row = tk.Frame(frame, bg="#141824", pady=4)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label, bg="#141824", fg="#A0A0B0", font=("Consolas", 9), width=20, anchor=tk.W).pack(side=tk.LEFT, padx=8)
            tk.Label(row, text=value, bg="#141824", fg="#58D68D", font=("Consolas", 9, "bold"), anchor=tk.W).pack(side=tk.LEFT)

        tk.Button(win, text="关闭", bg="#6E2020", fg="white", relief=tk.FLAT,
                  font=("Consolas", 10), command=win.destroy).pack(pady=10)

    def start_task(self):
        """开始运行注册任务"""
        if self.running_event.is_set():
            return
        n = max(1, min(100, self.thread_count.get()))
        self.running_event.set()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.thread_spin.config(state=tk.DISABLED)
        self.target_spin.config(state=tk.DISABLED) # Disable target spinbox too

        # Check if target success count is already met from previous runs in this session
        with self._lock:
            if self.success_count >= self.target_success_count.get():
                self._print_reg(f"[❤️] 已达到目标成功数 {self.target_success_count.get()}，无需启动新任务。")
                self._on_stop_complete() # Reset UI state
                return

        self._print_reg(f"\n[*] 启动 {n} 个注册线程...")
        self.worker_threads = []
        for i in range(n):
            t = threading.Thread(target=self._run_worker, args=(i+1,), daemon=True)
            t.start()
            self.worker_threads.append(t)

        # 监控线程：等所有工作线程结束后恢复 UI
        threading.Thread(target=self._monitor_workers, daemon=True).start()

    def stop_task(self):
        self._print_reg("\n[!] 正在发送停止信号... 所有线程将在当前账号周期完成后退出，请稍候...")
        self.running_event.clear()
        self.stop_btn.config(state=tk.DISABLED)

    def _monitor_workers(self):
        """等待所有工作线程退出后更新 UI 并打印统计"""
        for t in self.worker_threads:
            t.join()

        # 等待后台上传完成
        pending = [t for t in self.upload_threads if t.is_alive()]
        if pending:
            self._print_reg(f"\n[*] 等待 {len(pending)} 个上传任务完成...")
            for t in pending:
                t.join(timeout=30)

        total = self.success_count + self.fail_count
        self._print_reg("\n" + "="*50)
        self._print_reg(f"[*] 🏁 任务结束统计报告")
        self._print_reg(f"[*] 总计注册:   {total} 次")
        self._print_reg(f"[+] 注册成功:   {self.success_count} 个 ✅")
        self._print_reg(f"[×] 注册失败:   {self.fail_count} 个 ❌")
        self._print_reg("="*50)
        self._print_reg("[*] 所有线程已安全停止。")
        self.root.after(0, self._on_stop_complete)

    def _on_stop_complete(self):
        self.start_btn.config(state=tk.NORMAL)
        self.thread_spin.config(state=tk.NORMAL)
        self.target_spin.config(state=tk.NORMAL)

    def _run_worker(self, worker_id: int):
        """单个注册工作线程"""
        os.makedirs(TOKEN_OUTPUT_DIR, exist_ok=True)
        count = 0

        while self.running_event.is_set():
            # 检查是否达到目标成功数
            with self._lock:
                if self.success_count >= self.target_success_count.get():
                    self._print_reg(f"[*] [线程{worker_id}] 已达到目标成功数 {self.target_success_count.get()}，自动停止。")
                    self.running_event.clear() # Signal all threads to stop
                    break

            count += 1
            start_time = time.time()
            self._print_reg(f"\n[{datetime.now().strftime('%H:%M:%S')}][线程{worker_id}] >>> 第 {count} 次注册 <<<")

            try:
                result = run_full_flow(self.proxy)
                status = result[0]
                email = result[1]
                pwd = result[2]
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._print_reg(f"[-][线程{worker_id}] 💥 致命网络异常: {e}")
                status, email, pwd = "fail_exception", "", ""

            if status == "retry_40x":
                self._print_reg(f"[!][线程{worker_id}] 触发邮箱冷却/403，10秒后重试")
                with self._lock:
                    self.fail_count += 1
                self._update_stat()
                time.sleep(10)
                continue

            if status.startswith("{"):
                # 使用统一处理器
                if process_registration_result(status, email, pwd, upload=CPA_UPLOAD_ENABLED):
                    elapsed = time.time() - start_time
                    self._print_reg(f"[+][线程{worker_id}] 注册成功! {email} ({elapsed:.1f}s)")
                    with self._lock:
                        self.success_count += 1
                    self._update_stat()
                    if CPA_UPLOAD_ENABLED:
                        self._print_cpa(f"[{datetime.now().strftime('%H:%M:%S')}] 已加入上传队列: {email}")
                else:
                    self._print_reg(f"[×][线程{worker_id}] 数据处理失败 ❌")
                    with self._lock:
                        self.fail_count += 1
                    self._update_stat()
            elif email and pwd:
                elapsed = time.time() - start_time
                self._print_reg(f"[×][线程{worker_id}] 登陆失敗 ({status}) ❌ | {elapsed:.1f}s")
                with self._lock:
                    self.fail_count += 1
                self._update_stat()
            else:
                elapsed = time.time() - start_time
                self._print_reg(f"[×][线程{worker_id}] 流程失敗 ({status}) ❌ | {elapsed:.1f}s")
                with self._lock:
                    self.fail_count += 1
                self._update_stat()

            if not self.running_event.is_set(): break
            
            # --- 核心清理：生命周期结束任务 (无论成功/报错/限流) ---
            if email:
                threading.Thread(target=delete_alias_emails, args=(email,), daemon=True).start()
                
            wait = random.randint(self.sleep_min, self.sleep_max)
            if wait > 0:
                self._print_reg(f"[*][线程{worker_id}] 休息 {wait} 秒...")
                for _ in range(wait):
                    if not self.running_event.is_set(): break
                    time.sleep(1)

        self._print_reg(f"[*][线程{worker_id}] 已安全退出。")


def run_vps_mode():
    """无界面运行模式 (VPS) - 极速日志直通系统"""
    # 强制将全局 print 重定向到 log_reg，支持所有第三方模块输出同步到工作台
    global print
    def vps_print(*args, **kwargs):
        msg = " ".join(map(str, args))
        log_reg(msg)
    print = vps_print

    log_reg("\n" + "="*50)
    log_reg("🚀 OpenAI 自动注册系统 - VPS 服务模式 [稳定重构版]")
    log_reg(f"[*] 代理开启: {'是' if PROXY_ENABLED else '否'} ({PROXY})")
    log_reg(f"[*] 并发线程: {THREAD_COUNT}")
    log_reg(f"[*] 补货水位: {MIN_ACCOUNTS_THRESHOLD} 张")
    log_reg("="*50 + "\n")
    
    # 启动 CPA 运维任务
    maintenance_task.start()
    
    log_reg("[*] 仓管模式已开启：正在持续监视仓库健康度 & 自动执行补货逻辑...")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log_reg("\n[!] 停止运行...")
        sys.exit(0)

if __name__ == "__main__":
    if RUN_MODE == 1:
        run_vps_mode()
    else:
        root = tk.Tk()
        app = OpenApp(root)
        root.mainloop()
