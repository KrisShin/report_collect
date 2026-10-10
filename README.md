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

- 后端配置：`backend/.env`（已 gitignore，模板见 `backend/.env.example`）
- 初始管理员账号：`admin`，密码在 `backend/.env` 的 `ADMIN_INITIAL_PASSWORD`
- 已配置：飞书机器人、腾讯企业邮箱
- 待配置：`WECHAT_APP_ID`、`WECHAT_APP_SECRET`、`WECHAT_OAUTH_REDIRECT_URI`

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

已完成 M1（脚手架）+ M2（认证、数据模型、迁移、核心接口、前端页面骨架），11 个后端测试通过，前端生产构建通过。详见 `docs/00-准备与实施步骤.md` 第 19 节。
