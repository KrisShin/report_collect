# 报告收集系统

微信内 H5 报告收集 + 管理端（FastAPI + React 19 + SQLite）。

## 目录

```text
report_collect/
├─ backend/     FastAPI 后端（Python 3.12 / conda 环境 reportc）
├─ frontend/    Vite + React 19 SPA（客户端 /m + 管理端 /admin）
├─ docs/        需求、方案与实施步骤
└─ deploy/      部署配置（待补充）
```

## 环境

| 项 | 值 |
| --- | --- |
| Python | conda 环境 `reportc`：`C:\Users\HP\miniconda3\envs\reportc\python.exe` |
| Node | Node.js 22 / npm 11 |
| 后端端口 | `8600`（本机 7998–8197 被系统排除） |
| 前端端口 | `5173`（`/api` 代理到 8600） |

## 启动

```powershell
# 1. 后端
cd backend
C:\Users\HP\miniconda3\envs\reportc\python.exe -m uvicorn app.main:app --reload --port 8600

# 2. 前端（另开一个终端）
cd frontend
npm run dev
```

- 客户端：http://localhost:5173/m
- 管理端：http://localhost:5173/admin
- 接口文档：http://127.0.0.1:8600/docs
- 健康检查：http://127.0.0.1:8600/api/health

## 配置

- 后端配置：`backend/config.yaml`（已 gitignore，模板见 `backend/config.example.yaml`）
- 初始管理员账号：`admin`，密码在 `backend/config.yaml` 的 `admin.initial_password`
- 不读取任何环境变量；所有配置只在 `config.yaml` 中管理
- 已配置并验证：飞书机器人、腾讯企业邮箱 SMTP（2026-10-10 真实发送成功）
- 微信：方案 A —— 不做网页授权，仅校验 UA（`wechat.require_browser`）


## 多报告

- 管理端「报告管理」可新建/编辑/启停多个报告，并复制客户端链接
- 客户端地址：`/m/{report_id}`（按 uuid 填报）；`/m` 只提示"请用专用链接"，不提供报告选择接口与页面
- 客户端与后端双重 UA 校验：非微信内置浏览器直接提示"请在微信内打开"
- 报告可设置填报时间段（`start_at` / `end_at`）；未开始/已结束时客户端展示人性化提示页（接口返回 200 + state，阻止提交由前端与后端共同保证）
- AI 分析与飞书提醒在提交后的后台任务中执行；邮件发送也是后台任务（接口毫秒级返回，完成后再回写发送状态）
- 报告 id 为 `uuid4().hex`（32 位），不可猜测、不可遍历；报告标题与填写说明由后端返回
- 提交记录带 `report_id`，管理端可按报告筛选，导出/邮件附件含「报告」列
- 当前各报告字段相同（单位/职务/姓名/电话/邮箱），暂不支持每个报告自定义字段


## 数据处理与质量

- **提交唯一性**：同一报告内，**手机号 / 邮箱 / IP** 任一已存在即拒绝（409）。手机号与邮箱由数据库唯一约束保证，IP 由接口 + Redis 锁保证，可在 `security.unique_*_per_report` 分别开关
- **处理状态**：订阅 `is_processed / processed_at / processed_action`，发送邮件后自动标记为已处理；管理端可按"未处理/已处理"过滤
- **AI 质量判定**：接入 DeepSeek V4 Flash（`ai` 配置段），后台判定提交是否为垃圾/虚假信息，写入 `ai_flag / ai_score / ai_reason`；管理端可按"正常/可疑/判定失败/未判定"过滤，鼠标悬停查看理由
- **邮件收件人**：`mail.recipients`（当前 `krisshin@yeah.net`）；为空时回退为提交人邮箱
- **测试拦截**：当前在 `mailer.py` 顶部用 `TEST_INBOX = "krisshin@yeah.net"` 硬编码，所有邮件统一只发该测试邮箱；发布前删除该常量并恢复业务收件人
- **邮件模板**：`backend/app/templates/email_report.html`，Jinja2 渲染，预览见 `docs/sample-email-preview.html`


## 界面

- 客户端：深蓝 + 金色科研风格，报告标题来自后端，底部固定提交按钮；提交成功后为纯结果页，**不提供任何返回/跳转按钮**
- 管理端：渐变头部 + 导航胶囊，统计卡片；桌面端筛选行内展示，移动端筛选收进抽屉；表格横向自适应（默认宽度 1900px 级别，列宽已加大）


## 生产与安全

- 详细安全加固报告：`docs/30-安全加固报告.md`
- 并发与限流依赖 Redis（未启用时自动降级为进程内实现）：
  - 提交限流（IP / 手机号）、重复提交分布式锁
  - 管理端登录失败锁定、JWT 注销黑名单
  - AI / 飞书 / 邮件任务队列，由 `python -m app.worker` 独立消费
- 部署文件：`deploy/docker-compose.yml`（Redis）、`deploy/reportc-worker.service`（worker）、`deploy/README.md`


## 一键部署（生产 / Linux）

```bash
sudo ./deploy.sh --domain report.example.com
# 已有证书：
sudo ./deploy.sh --domain report.example.com \
  --cert /etc/letsencrypt/live/report.example.com/fullchain.pem \
  --key  /etc/letsencrypt/live/report.example.com/privkey.pem
```

脚本会完成：虚拟环境与依赖 → 前端构建 → `alembic upgrade head` → 写入 systemd（**gunicorn + uvicorn worker** 的 API 服务 + Redis worker）→ 配置 Nginx（含 `X-Forwarded-For`）→ 重启服务。

参数见 `./deploy.sh --help`；`--no-nginx`、`--no-systemd`、`--skip-frontend`、`--skip-system-deps` 可按需跳过。

## 测试与构建

```powershell
# 后端
cd backend
C:\Users\HP\miniconda3\envs\reportc\python.exe -m pytest
C:\Users\HP\miniconda3\envs\reportc\python.exe -m ruff check .

# 前端
cd frontend
npm run build
```

## 数据库

```powershell
cd backend
C:\Users\HP\miniconda3\envs\reportc\python.exe -m alembic upgrade head
```

SQLite 文件：`backend/data/app.db`（已 gitignore）。生产环境每日备份，使用 `sqlite3 app.db ".backup ..."`。

## 当前状态

已完成 M1（脚手架）+ M2（认证、数据模型、迁移、核心接口、前端页面骨架），11 个后端测试通过，前端生产构建通过；前端已按客户端/管理端代码分割（客户端不加载 antd）。详见 `docs/00-准备与实施步骤.md` 第 19 节。
