# 📧 IMAP 邮件网关配置手册 (Gmail)

> **核心提示**：为了让机器人能够自动化读取验证码，你必须为你的“主邮箱”（用于接收所有转发邮件的中心邮箱）开启 IMAP 权限并生成 **16 位应用专用密码**。直接使用邮箱登录密码会导致登录失败。

---

## 💎 Gmail 配置流程 

### 1. 开启 IMAP 访问权限
1.  登录 [Gmail 网页版](https://mail.google.com/)。
2.  点击右上角 **“齿轮”图标** -> **“查看所有设置”**。
3.  点击 **“转发和 POP/IMAP”** 选项卡。
4.  在 **“IMAP 访问”** 栏中，勾选 **“开启 IMAP”**。
5.  点击页面最下方的 **“保存更改”**。

### 2. 生成 16 位应用专用密码 (必需)
1.  访问 [Google 账号安全中心](https://myaccount.google.com/security)。
2.  确保 **“两步验证” (2-Step Verification)** 已开启。
3.  在页面最下方搜索或进入 **“应用专用密码” (App passwords)**。
    *   *快速跳转链接*: [生成应用专用密码](https://myaccount.google.com/apppasswords)
4.  **生成密码**：
    *   为应用命名（如 `OpenAI-Reg`）。
    *   点击 **“创建” (Create)**。
5.  **记录密码**：复制弹出的 **16 位黄色代码**（例如 `xxxx xxxx xxxx xxxx`）。这个密码将填入 `.env` 的 `IMAP_PASS`。

---