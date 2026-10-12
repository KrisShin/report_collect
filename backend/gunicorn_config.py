"""Gunicorn 配置：与服务器上其他项目保持一致的部署方式（--daemon 后台常驻）。"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 仅监听本机，由 Caddy 反向代理对外提供服务（不直接对外暴露）
bind = "127.0.0.1:9200"
worker_class = "uvicorn.workers.UvicornWorker"
workers = 3

timeout = 60
graceful_timeout = 30
keepalive = 5

# 日志
accesslog = str(BASE_DIR / "logs" / "access.log")
errorlog = str(BASE_DIR / "logs" / "error.log")
loglevel = "info"
capture_output = True
