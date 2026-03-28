#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import threading
import subprocess
from datetime import datetime

# ====================================================
# 1. 环境准备
# ====================================================

def check_and_install_deps():
    """静默智检 Python 库"""
    required_libs = [
        ("requests", "requests"),
        ("curl_cffi", "curl_cffi"),
        ("dotenv", "python-dotenv"),
        ("socks", "PySocks")
    ]
    for mod_name, pip_name in required_libs:
        try:
            __import__(mod_name)
        except ImportError:
            os.system(f"{sys.executable} -m pip install {pip_name}")

# ====================================================
# 2. 日志流转逻辑 (实时工作台)
# ====================================================

def stream_logs(pipe, prefix):
    """实时读取并打印子进程输出"""
    while True:
        line = pipe.readline()
        if not line:
            break
        # 此时 line 已经是字符串，不再需要 decode
        log_line = line.strip()
        if log_line:
            print(f"[{prefix}] {log_line}")
    pipe.close()

def run_services():
    """拉起两个脚本并实时聚合日志"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚀 系统正在初始化，准备进入全量工作台模式...")
    
    # 彻底关掉旧进程
    os.system("pkill -9 -f open.py && pkill -9 -f kata_cpa_server.py && pkill -9 -f CLIProxyAPI")

    # 1. 启动 CPA 仓库服务器 (开启 text=True 模式消灭警告)
    p_cpa = subprocess.Popen(
        [sys.executable, "kata_cpa_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        encoding='utf-8',
        errors='ignore'
    )
    
    # 2. 启动 注册机器人
    p_bot = subprocess.Popen(
        [sys.executable, "open.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        encoding='utf-8',
        errors='ignore'
    )

    # 3. 启动两个线程实时输出
    t1 = threading.Thread(target=stream_logs, args=(p_cpa.stdout, "CPA-Server"), daemon=True)
    t2 = threading.Thread(target=stream_logs, args=(p_bot.stdout, "Bot-Worker"), daemon=True)
    
    t1.start()
    t2.start()

    print("\n" + "="*50)
    print("✅ 系统已全量运行。下方显示实时运行数据：")
    print("="*50 + "\n")

    # 只要任何一个子进程还活着，主进程就等着 (实现实时监视)
    try:
        p_cpa.wait()
        p_bot.wait()
    except (KeyboardInterrupt, SystemExit):
        p_cpa.terminate()
        p_bot.terminate()
        sys.exit(0)

if __name__ == "__main__":
    # 执行智检
    check_and_install_deps()
    # 进入工作台
    run_services()
