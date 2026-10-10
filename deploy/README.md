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
