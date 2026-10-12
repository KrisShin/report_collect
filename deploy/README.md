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
