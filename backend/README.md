# 报告收集系统 · 后端

使用 conda 环境 `reportc`（Python 3.12）。

## 启动

```powershell
cd backend
C:\Users\HP\miniconda3\envs\reportc\python.exe -m uvicorn app.main:app --reload --port 8600
```

- 健康检查：http://127.0.0.1:8600/api/health
- 接口文档：http://127.0.0.1:8600/docs

## 数据库

- 默认 SQLite：`backend/data/app.db`（已 gitignore）
- 迁移：`alembic upgrade head`

## 测试

```powershell
C:\Users\HP\miniconda3\envs\reportc\python.exe -m pytest
```
