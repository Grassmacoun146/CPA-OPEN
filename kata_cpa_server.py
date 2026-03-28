import os
import subprocess
import urllib.request
import tarfile
import sys
import stat

import platform
import json

PORT = os.environ.get("SERVER_PORT", "8317")
MGMT_SECRET = "990299"

# 设置 5 个 API Key
CLIENT_API_KEYS = [
    "sk-kata-key-1",
    "sk-kata-key-2",
    "sk-kata-key-3",
    "sk-kata-key-4",
    "sk-kata-key-5"
]

print(f"==================================================")
print(f"[*] 初始化 Kata Python 容器 ... 唯一端口: {PORT}")
print(f"==================================================")

config_yaml = f"""host: '0.0.0.0'
port: {PORT}

remote-management:
  allow-remote: true
  secret-key: '{MGMT_SECRET}'
  disable-control-panel: false
  panel-github-repository: 'https://github.com/router-for-me/Cli-Proxy-API-Management-Center'

auth-dir: './credentials'

api-keys:
  - '{CLIENT_API_KEYS[0]}'
  - '{CLIENT_API_KEYS[1]}'
  - '{CLIENT_API_KEYS[2]}'
  - '{CLIENT_API_KEYS[3]}'
  - '{CLIENT_API_KEYS[4]}'

oauth-model-alias:
  codex:
    - name: "gpt-5"
      alias: "gpt-4o"
"""
with open("config.yaml", "w", encoding="utf-8") as f:
    f.write(config_yaml)

os.makedirs("credentials/codex", exist_ok=True)

def find_binary():
    for f in os.listdir('.'):
        if 'cli' in f.lower() and not (f.endswith('.js') or f.endswith('.py') or f.endswith('.yaml') or f.endswith('.gz')):
            return "./" + f
    return None

def get_latest_version():
    try:
        # 使用 GitHub API 获取最新版本信息，更可靠且速度快
        url = "https://api.github.com/repos/router-for-me/CLIProxyAPI/releases/latest"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get("tag_name", "unknown")
    except Exception as e:
        print(f"[*] 通过 API 获取最新版本失败: {e}，尝试通过页面获取...")
        try:
            url = "https://github.com/router-for-me/CLIProxyAPI/releases/latest"
            with urllib.request.urlopen(url) as response:
                return response.geturl().split('/')[-1]
        except:
            return "unknown"

def get_current_version(bin_path):
    try:
        result = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=3)
        return result.stdout.lower() + result.stderr.lower()
    except Exception:
        pass
    return "unknown"

def download_engine(version):
    machine = platform.machine().lower()
    if "x86_64" in machine or "amd64" in machine:
        arch = "amd64"
    elif "aarch64" in machine or "arm64" in machine:
        arch = "arm64"
    else:
        arch = "amd64"

    print(f"[*] 检测到系统架构: {arch.upper()}，正在拉取全网最新版本 ({version}) 的 Linux 引擎...")
    # 注意：URL 里的版本号需要去掉 'v' 前缀
    v_num = version.lstrip('v')
    url = f"https://github.com/router-for-me/CLIProxyAPI/releases/download/{version}/CLIProxyAPI_{v_num}_linux_{arch}.tar.gz"
    
    try:
        urllib.request.urlretrieve(url, "cpa.tar.gz")
        with tarfile.open("cpa.tar.gz", "r:gz") as tar:
            tar.extractall(path=".")
        os.remove("cpa.tar.gz")
        print(f"[*] 最新版本 {version} 下载并解压完成。")
        return True
    except Exception as e:
        print(f"[!] 下载引擎失败: {e}")
        return False

latest_v = get_latest_version()
bin_name = find_binary()

if bin_name and latest_v != "unknown":
    curr_v_log = get_current_version(bin_name)
    if latest_v.lstrip('v') not in curr_v_log:
        print(f"[*] 发现新版本 {latest_v} (当前运行环境可能是旧版)，正在强制拉取更新...")
        try:
            os.remove(bin_name)
        except:
            pass
        bin_name = None

if not bin_name:
    if latest_v == "unknown":
        # 如果获取不到最新版本，尝试用 6.9.1/6.9.2 作为兜底但尽量避免
        latest_v = "v6.9.2"
    download_engine(latest_v)
    bin_name = find_binary()

if bin_name:
    st = os.stat(bin_name)
    os.chmod(bin_name, st.st_mode | stat.S_IEXEC)
else:
    print("[!] 无法定位引擎二进制文件，请检查当前目录。")
    sys.exit(1)

print(f"[*] 引擎 (${bin_name}) 加载完成，接管一切心跳...")
process = subprocess.Popen([bin_name], stdout=sys.stdout, stderr=sys.stderr)
try:
    process.wait()
except KeyboardInterrupt:
    process.terminate()
