# ⚙️ 环境配置 (Env Configuration) 指南

[⬅️ 返回主页](./README.md)

> **🚀 核心操作 (极其重要)**：
> 在开始任何配置前，必须先将项目根目录下的 **`.env.example`** 文件重命名为 **`.env`**。
> **如果找不到 `.env` 文件，系统将无法加载任何配置并导致启动报错！**

---

## 💎 第一步：初始化配置文件

1.  找到文件：在项目文件夹中找到文件名为 `.env.example` 的模板。
2.  执行重命名：右键点击该文件，选择“重命名”，将其改为 **`.env`** (注意：前面有一个点)。
3.  开始编辑：使用记事本或 VS Code 打开重命名后的 `.env` 文件进行参数修改。

---

## 💎 第二步：基础参数详解

| 变量名 | 推荐设置 | 说明 |
| :--- | :--- | :--- |
| `RUN_MODE` | `0` 或 `1` | **0**: 本地 GUI 模式 (Windows)；**1**: 无界面 VPS 模式 (Linux)。 |
| `PROXY_ENABLED` | `1` | **1**: 开启代理；**0**: 关闭代理 (注册 OpenAI 必需开启)。 |
| `PROXY` | `http://...` | 代理地址，例：`http://127.0.0.1:10808` (本地) 或 `http://user:pass@ip:port` (VPS)。 |
| `EMAIL_LIST` | `yourdomain.com` | 支持多个 Catch-all 域名或单个邮箱。多个可用逗号分隔。 |
| `IMAP_USER` | `yourname@gmail.com` | 系统主控收信箱 (中心邮箱)。 |
| `IMAP_PASS` | `xxxx xxxx xxxx xxxx` | 必须填入 **16 位应用专用密码**，中间可带空格。 |
| `IMAP_SERVER` | `imap.gmail.com` | 固定为 Gmail 的 IMAP 地址。 |
| `CPA_UPLOAD_ENABLED` | `0` 或 `1` | 注册成功后是否推送至 CPA 仓库管理机。 |
| `THREAD_COUNT` | `1-5` | 并发线程数。 |

---

## 💎 第三步：全场景配置方案对比 (Comparison)

### 🚀 方案 A：本机 GUI 调试 (Local Windows)
- **RUN_MODE** = `0`
- **PROXY** = `http://127.0.0.1:10808` (取决于本地代理软件端口)
- **CPA_UPLOAD_ENABLED** = `0` (暂不上传仓库，存留在 `credentials` 文件夹)
- **THREAD_COUNT** = `1` (推荐由单一线程发起，方便调试)

### 🚀 方案 B：VPS 无头服务器 (Linux VPS)
- **RUN_MODE** = `1`
- **PROXY** = `http://user:pass@ip:port` (需配置稳定的住宅 IP 或优质节点)
- **CPA_UPLOAD_ENABLED** = `1` (注册成功自动推送至后端)
- **CPA_MAINTENANCE_ENABLED** = `1` (自动巡检管理仓库活号水位)
- **MIN_ACCOUNTS_THRESHOLD** = `30` (少于 30 个活号自动补注册)
- **THREAD_COUNT** = `2-5` (根据带宽和 CPU 配置设定)

---

## 💎 第四步：常见参数进阶技巧
- **GMAIL_TAG_LEN**: 默认为 `8`。建议维持在 4-8 之间。
- **COOL_DOWN_HOURS**: 默认 `24`。当某个主邮箱出现封号风控时，系统会自动冷却该邮箱的时间。
- **TOKEN_OUTPUT_DIR**: 默认为 `credentials`。所有注册成功的 Token 文件都会保存在此处。

---