#!/usr/bin/env bash
# =============================================================================
# 报告收集系统 · 一键部署脚本（生产 / Linux）
#
# 功能：虚拟环境 → 依赖 → 前端构建 → 数据库迁移 → systemd(gunicorn + worker)
#       → Nginx 反向代理（含 X-Forwarded-For，保证限流按真实 IP 生效）
#
# 用法：
#   sudo ./deploy.sh --domain report.example.com
#   sudo ./deploy.sh --domain report.example.com --cert /etc/letsencrypt/live/report.example.com/fullchain.pem \
#                                              --key  /etc/letsencrypt/live/report.example.com/privkey.pem
#   sudo ./deploy.sh --domain report.example.com --no-nginx     # 只部署后端服务
#
# 常用参数：
#   --domain <域名>     必填（除非 --no-nginx）
#   --port <端口>       后端监听端口，默认 8600
#   --workers <N>       gunicorn worker 数，默认 2（SQLite 建议 2~4）
#   --user <用户>       运行服务的系统用户，默认 www-data
#   --cert/--key        HTTPS 证书路径（不传则只配置 80 端口，后续用 certbot 签发）
#   --no-nginx          跳过 Nginx 配置
#   --no-systemd        跳过 systemd 配置（仅安装依赖 + 构建 + 迁移）
#   --skip-frontend     跳过前端构建
#   --skip-system-deps  跳过 apt 安装系统依赖
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
CONFIG_FILE="$BACKEND_DIR/config.yaml"

DOMAIN=""
API_PORT="8600"
WORKERS="2"
SERVICE_USER="www-data"
SSL_CERT=""
SSL_KEY=""
USE_NGINX=1
USE_SYSTEMD=1
BUILD_FRONTEND=1
INSTALL_SYS_DEPS=1

log()  { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn ]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --port) API_PORT="${2:-}"; shift 2 ;;
    --workers) WORKERS="${2:-}"; shift 2 ;;
    --user) SERVICE_USER="${2:-}"; shift 2 ;;
    --cert) SSL_CERT="${2:-}"; shift 2 ;;
    --key) SSL_KEY="${2:-}"; shift 2 ;;
    --no-nginx) USE_NGINX=0; shift ;;
    --no-systemd) USE_SYSTEMD=0; shift ;;
    --skip-frontend) BUILD_FRONTEND=0; shift ;;
    --skip-system-deps) INSTALL_SYS_DEPS=0; shift ;;
    -h|--help) usage ;;
    *) die "未知参数：$1（--help 查看用法）" ;;
  esac
done

# ---------------------------------------------------------------- 前置检查
[[ "$(uname -s)" == "Linux" ]] || die "本脚本用于 Linux 生产环境（当前：$(uname -s)）"
[[ -d "$BACKEND_DIR" && -d "$FRONTEND_DIR" ]] || die "请在项目根目录执行（需存在 backend/ 与 frontend/）"

if [[ $USE_NGINX -eq 1 && -z "$DOMAIN" ]]; then
  die "缺少 --domain（或使用 --no-nginx 跳过 Nginx）"
fi

if [[ $USE_SYSTEMD -eq 1 || $USE_NGINX -eq 1 ]]; then
  [[ "$(id -u)" -eq 0 ]] || die "配置 systemd / Nginx 需要 root：请用 sudo 执行"
fi

find_python() {
  for candidate in python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
        echo "$candidate"; return 0
      fi
    fi
  done
  return 1
}

if [[ $INSTALL_SYS_DEPS -eq 1 ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    log "安装系统依赖（python3.12 / nginx / redis / nodejs）"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip nginx redis-server curl ca-certificates
    if ! command -v node >/dev/null 2>&1; then
      warn "未检测到 Node.js，可参考 https://nodejs.org 安装 20+ 版本；跳过 apt 安装以免版本过旧"
    fi
  else
    warn "非 apt 系统，跳过系统依赖安装，请自行确保 python3.12 / nginx / redis / node 已安装"
  fi
fi

PYTHON_BIN="$(find_python)" || die "未找到 Python 3.12+，请先安装"

# ---------------------------------------------------------------- 后端依赖
log "创建虚拟环境并安装后端依赖"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q

# ---------------------------------------------------------------- 配置文件
if [[ ! -f "$CONFIG_FILE" ]]; then
  cp "$BACKEND_DIR/config.example.yaml" "$CONFIG_FILE"
  warn "已生成 $CONFIG_FILE（模板），请填写数据库/飞书/邮箱/AI/Redis 等配置后重新执行部署"
fi

REDIS_ENABLED=0
if "$VENV_DIR/bin/python" - "$CONFIG_FILE" <<'PY'
import sys
import yaml

cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
raise SystemExit(0 if (cfg.get("redis") or {}).get("enabled") else 1)
PY
then
  REDIS_ENABLED=1
fi
[[ $REDIS_ENABLED -eq 1 ]] || warn "Redis 未启用：限流/登录锁定将退化为进程内实现，且 gunicorn 多 worker 下不共享状态（生产强烈建议开启）"

# ---------------------------------------------------------------- 前端构建
if [[ $BUILD_FRONTEND -eq 1 ]]; then
  command -v npm >/dev/null 2>&1 || die "未找到 npm，无法构建前端（或用 --skip-frontend 跳过）"
  log "构建前端（Vite）"
  pushd "$FRONTEND_DIR" >/dev/null
  if [[ -f package-lock.json ]]; then npm ci --silent; else npm install --silent; fi
  npm run build
  popd >/dev/null
fi

# ---------------------------------------------------------------- 数据库迁移
log "执行数据库迁移（alembic upgrade head）"
pushd "$BACKEND_DIR" >/dev/null
"$VENV_DIR/bin/python" -m alembic upgrade head
popd >/dev/null

mkdir -p "$BACKEND_DIR/data" "$BACKEND_DIR/logs"

# 系统用户存在性
if [[ $USE_SYSTEMD -eq 1 ]]; then
  id -u "$SERVICE_USER" >/dev/null 2>&1 || die "系统用户不存在：$SERVICE_USER（可用 --user 指定）"
  log "调整目录权限（$SERVICE_USER）"
  chown -R "$SERVICE_USER":"$SERVICE_USER" "$BACKEND_DIR/data" "$BACKEND_DIR/logs"
  chown "$SERVICE_USER":"$SERVICE_USER" "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"

  log "写入 systemd 服务（gunicorn + uvicorn worker）"
  cat > /etc/systemd/system/reportc-api.service <<EOF
[Unit]
Description=Report Collection API (gunicorn)
After=network.target redis-server.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$BACKEND_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV_DIR/bin/gunicorn app.main:app \\
  --worker-class uvicorn.workers.UvicornWorker \\
  --workers $WORKERS \\
  --bind 127.0.0.1:$API_PORT \\
  --timeout 60 --graceful-timeout 30 --keep-alive 5 \\
  --access-logfile - --error-logfile - --capture-output
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  if [[ $REDIS_ENABLED -eq 1 ]]; then
    log "写入 systemd 服务（Redis worker）"
    cat > /etc/systemd/system/reportc-worker.service <<EOF
[Unit]
Description=Report Collection Redis Worker
After=network.target redis-server.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$BACKEND_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV_DIR/bin/python -m app.worker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  fi

  systemctl daemon-reload
  systemctl enable reportc-api >/dev/null 2>&1 || true
  systemctl restart reportc-api
  if [[ $REDIS_ENABLED -eq 1 ]]; then
    systemctl enable reportc-worker >/dev/null 2>&1 || true
    systemctl restart reportc-worker
  fi
fi

# ---------------------------------------------------------------- Nginx
if [[ $USE_NGINX -eq 1 ]]; then
  log "配置 Nginx（$DOMAIN）"
  if [[ -n "$SSL_CERT" && -n "$SSL_KEY" ]]; then
    REDIRECT_BLOCK=$(cat <<REDIRECT
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

REDIRECT
)
    LISTEN_LINE="listen 443 ssl http2;"
    SSL_LINES="ssl_certificate $SSL_CERT;
    ssl_certificate_key $SSL_KEY;
    ssl_protocols TLSv1.2 TLSv1.3;"
  else
    REDIRECT_BLOCK=""
    LISTEN_LINE="listen 80;"
    SSL_LINES=""
  fi

  cat > /etc/nginx/sites-available/reportc.conf <<EOF
$REDIRECT_BLOCK
server {
    $LISTEN_LINE
    $SSL_LINES
    server_name $DOMAIN;

    client_max_body_size 20m;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript image/svg+xml;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # API：透传真实 IP，限流才能按访客 IP 生效
    location /api/ {
        proxy_pass http://127.0.0.1:$API_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    # 前端静态资源（SPA）
    location / {
        root $FRONTEND_DIR/dist;
        try_files \$uri \$uri/ /index.html;
        expires 7d;
    }
}
EOF

  ln -sf /etc/nginx/sites-available/reportc.conf /etc/nginx/sites-enabled/reportc.conf
  if [[ -f /etc/nginx/sites-enabled/default ]]; then
    rm -f /etc/nginx/sites-enabled/default
  fi
  nginx -t
  systemctl reload nginx
fi

# ---------------------------------------------------------------- 结果
API_STATUS="未管理（--no-systemd）"
if [[ $USE_SYSTEMD -eq 1 ]]; then
  sleep 2
  if systemctl is-active --quiet reportc-api; then API_STATUS="running"; else API_STATUS="failed（查看 journalctl -u reportc-api -n 50）"; fi
fi

cat <<EOF

============================================================
 部署完成
============================================================
 项目目录     : $APP_DIR
 配置文件     : $CONFIG_FILE
 虚拟环境     : $VENV_DIR
 后端监听     : 127.0.0.1:$API_PORT（gunicorn $WORKERS workers）
 Redis        : $([[ $REDIS_ENABLED -eq 1 ]] && echo 已启用 || echo 未启用（降级模式）)
 API 服务状态 : $API_STATUS
 访问地址     : $([[ $USE_NGINX -eq 1 ]] && echo "http${SSL_CERT:+s}://$DOMAIN" || echo "http://127.0.0.1:$API_PORT")
------------------------------------------------------------
 常用命令
   查看状态 : systemctl status reportc-api
   查看日志 : journalctl -u reportc-api -f
   worker   : journalctl -u reportc-worker -f
   重启     : systemctl restart reportc-api reportc-worker
   健康检查 : curl http://127.0.0.1:$API_PORT/api/health
------------------------------------------------------------
 上线前务必确认
   [ ] $CONFIG_FILE 已填写正确，且 app.env = production
   [ ] 删除 backend/app/services/mailer.py 的 TEST_INBOX 硬编码
   [ ] 修改初始管理员密码（admin）
   [ ] Redis 已启用并设置强密码（redis.enabled = true）
   [ ] HTTPS 证书已配置（无证书时执行：certbot --nginx -d $DOMAIN）
============================================================
EOF
