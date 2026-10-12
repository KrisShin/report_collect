# 部署说明（生产）

## 1. Redis

```bash
cd deploy
export REDIS_PASSWORD='<强密码>'
docker compose up -d
```

`config.yaml` 中对应配置（生产建议只监听 127.0.0.1）：

```yaml
redis:
  enabled: true
  url: redis://:<强密码>@127.0.0.1:6379/0
  key_prefix: reportc
  job_queue_key: jobs
```

## 2. Worker（消费 AI / 飞书 / 邮件任务）

```bash
sudo cp deploy/reportc-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reportc-worker
```

> 未启用 Redis 时，任务回退为 FastAPI BackgroundTasks（进程内执行，服务重启会丢任务）。

## 3. Nginx 关键配置

```nginx
server {
    listen 443 ssl http2;
    server_name report.example.com;

    # 记录真实访客 IP（后端会读取 X-Forwarded-For）
    location /api/ {
        proxy_pass http://127.0.0.1:8600;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SPA 静态资源
    location / {
        root /opt/report_collect/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # 安全响应头（后端也会带，这里可再加 CSP）
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
}
```

## 4. 上线前检查

- [ ] `redis.enabled: true`，Redis 使用强密码、仅监听 127.0.0.1
- [ ] `app.env: production`（启用 UA 强制校验、Cookie Secure、HSTS）
- [ ] `app.cors_origins` 只保留正式域名
- [ ] 删除 `mailer.py` 中的 `TEST_INBOX` 硬编码
- [ ] 修改初始管理员密码
- [ ] 全站 HTTPS；SQLite 文件每日备份
- [ ] `diagnostics.log_client_requests: false` 或保留但确认已脱敏

## 5. 前端发布（重要）

服务器没有 Node.js，前端在本地构建后上传：

```powershell
# 本地
cd frontend
npm run build
scp -i <key> -r dist/* ecs-user@<server>:/home/ecs-user/Projects/report_collect/frontend/dist/
```

上传后**必须修正权限**：Caddy 以 `caddy` 用户运行，若 `dist/assets`
目录权限是 700，Caddy 读不到 JS/CSS，`try_files` 会回退返回 index.html，
浏览器拿到的是 HTML 而不是脚本 → **页面白屏**。

```bash
chmod -R u=rwX,go=rX /home/ecs-user/Projects/report_collect/frontend/dist
```

> 项目根目录的 `restart.sh` 已内置该 `chmod`，执行 `./restart.sh` 会自动修正，
> 因此发布前端后直接运行 `./restart.sh` 即可。

### 排查白屏的快速方法

```bash
# 正常应返回 text/javascript；若返回 text/html 说明静态资源没读到（权限问题）
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" https://<域名>/assets/<某个chunk>.js
```

## 6. 飞书卡片回调（一键重试失败）

### 开放平台配置

| 项 | 值 |
| --- | --- |
| 卡片请求地址 | `https://report.toputils.top/api/feishu/card/callback` |
| Verification Token | 填入 `backend/config.yaml` 的 `feishu.verification_token` |
| Encrypt Key | 建议开启并填入 `backend/config.yaml` 的 `feishu.encrypt_key` |

`config.yaml` 对应配置：

```yaml
feishu:
  app_id: cli_xxxxxxxx
  app_secret: xxxxxxxx
  chat_id: oc_xxxxxxxx            # 只允许该群的卡片动作
  verification_token: xxxxxxxx    # 与开放平台一致
  encrypt_key: xxxxxxxx           # 启用加密套件后必填
```

注意：应用需要开通 `im:message:send_as_bot` 权限，并**把机器人拉进目标群**，否则发消息会报 `230002 Bot/User can NOT be out of the chat`。

### 安全校验（三道）

1. `verification_token` 必须一致（URL 验证握手只校验这一项）
2. 卡片动作必须来自配置的群 `open_chat_id`
3. 配置 `encrypt_key` 后：AES-256-CBC 解密载荷 + 校验 `X-Lark-Signature`
   `signature = sha256(timestamp + nonce + encrypt_key + body)`

另有频率限制：同一批失败邮件 5 分钟只允许触发一次重试，重试幂等。

## 7. 邮件静态附件

把文件放到（服务器）：

```
/home/ecs-user/Projects/report_collect/backend/mail_attachments/
```

- 目录内所有非隐藏文件会**自动附加到每封邮件**，并出现在邮件正文的"其他附件"清单
- 只给某个报告附带：放到 `mail_attachments/<报告ID>/`
- 超 `mail.max_attachment_mb`（默认 20MB）自动跳过并记日志
- 修改**不需要重启**，每次发信实时扫描
- 注意：附件会随每封邮件发送，单文件建议 ≤2MB

```yaml
mail:
  attachment_dir: mail_attachments
  max_attachment_mb: 20
```

## 8. 邮件发送规则（当前实现）

| 项 | 说明 |
| --- | --- |
| 收件人 | 勾选哪几条就发给哪几个本人（方案 A） |
| 附件 | **只带 `mail_attachments/` 里的文件**，不再自动生成 xlsx（导出 xlsx 仍可在管理端"一键导出"下载） |
| 节流 | 每封间隔 `mail.send_interval_seconds`（当前 3 秒） |
| 状态 | 成功 → `sent` + `is_processed`；失败 → **状态不变**，只记 `mail_error` |
| 进度 | 发送中每 30 秒飞书汇报一次（纯文本，无按钮） |
| 完成 | 全部成功 → 纯文本汇报；有失败 → 交互卡片 + 一键重试按钮 |
| 重试 | 点按钮 → 飞书回调 → 冷却 `retry_delay_seconds`（300 秒）→ 只重试失败邮箱 |
| 测试门控 | **已取消**（真实发送）。如需临时拦截，取消 `app/services/mailer.py` 里那一行的注释即可 |
