# 🤖 OpenAI-Reg-Master (CPA 注册机智控版)

> **极简、强大、全自动。** 工业级 OpenAI 批量注册与 CPA 自动化仓库维护旗舰方案。

---

## 🧭 项目导视 (Fast Navigation)

为了助您快速上手，我们提供了全维度的配置与部署手册。点击下方图标直接跳转：

| 手册名称 | 核心内容 | 快捷访问 |
| :--- | :--- | :--- |
| **🌍 环境变量指南** | `.env` 核心参数详解与全场景方案对比 | [👉 点击阅读](./env_guide.md) |
| **📧 IMAP 配置手册** | Gmail 开启 IMAP 与 16 位专用密码生成流程 | [👉 点击阅读](./imap_setup.md) |
| **🚀 KataBump 部署** | VPS (KataBump) 一键挂机与服务器保活续期 | [👉 点击阅读](./kata_deploy.md) |
| **🏗️ 运维手册 (Pro)** | 系统架构解析、物理清理策略与核心运维逻辑 | [👉 点击阅读](./open_doc.md) |

---

## 💎 系统亮点 (Project Highlights)

- **🚀 双模作战**: 支持 Windows 本机 GUI 调试与 VPS Linux 无头挂机模式。
- **🛡️ 隐身对抗**: 集成 `curl_cffi` 深度模拟 Chrome/iOS 指纹，轻松绕过 Cloudflare 与 OpenAI WAF 监测。
- **📧 裂变收信**: 适配 Gmail (Plus/Dot) 与 Catch-all 模式，仅需一个主邮箱实现无限极注册。
- **📦 CPA 智控**: 内置 API 仓库服务端，支持自动补货、测活盘点、失效号清理。
- **⚡ 实时监控**: 聚合双端日志，秒级同步注册进度与仓库水位。

---

## 🛠️ 快速起步

### 1. 环境准备
- **Python**: 3.8+ (推荐 3.10+)
- **安装依赖**:
  ```bash
  pip install requests curl_cffi python-dotenv PySocks
  ```

### 2. 核心启动
1. **重命名配置**: 将 `.env.example` -> `.env`
2. **快速运行**: 本机调试或 VPS 挂机一键启动：
   ```bash
   python deploy.py
   ```

---


## ⚠️ 开发者提醒
1. **安全第一**: 严禁硬编码敏感信息。
2. **代理质量**: OpenAI 对 IP 风控极严，建议使用独享住宅代理。

---