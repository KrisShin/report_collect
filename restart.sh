#!/usr/bin/env bash
# =============================================================================
# 报告收集系统 · 服务管理脚本（无 systemd，gunicorn daemon + Redis worker）
#
# 用法：
#   ./restart.sh            # 重启 API + worker（默认）
#   ./restart.sh start      # 只启动
#   ./restart.sh stop       # 只停止
#   ./restart.sh status     # 查看状态
#
# 说明：只匹配本项目的 gunicorn（app.main:app）与 worker（-m app.worker），
#       不会影响服务器上其他应用。
# =============================================================================
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
VENV="$APP_DIR/.venv"
GUNICORN="$VENV/bin/gunicorn"
PYTHON="$VENV/bin/python"
LOG_DIR="$BACKEND_DIR/logs"
API_PORT="${API_PORT:-9200}"

API_PATTERN='gunicorn -c gunicorn_config.py app\.main:app'
WORKER_PATTERN='python -m app\.worker'

log() { printf '[restart] %s\n' "$*"; }
die() { printf '[error] %s\n' "$*" >&2; exit 1; }

api_pids() { pgrep -f "$API_PATTERN" 2>/dev/null || true; }
worker_pids() { pgrep -f "$WORKER_PATTERN" 2>/dev/null || true; }

stop_api() {
  local pids
  pids="$(api_pids)"
  if [[ -z "$pids" ]]; then
    log "API 未在运行"
    return 0
  fi
  log "停止 API (pids: $(echo "$pids" | tr '\n' ' '))"
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 15); do
    [[ -z "$(api_pids)" ]] && break
    sleep 1
  done
  pids="$(api_pids)"
  if [[ -n "$pids" ]]; then
    log "优雅停止超时，强制结束"
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi
  log "API 已停止"
}

stop_worker() {
  local pids
  pids="$(worker_pids)"
  if [[ -z "$pids" ]]; then
    log "worker 未在运行"
    return 0
  fi
  log "停止 worker (pids: $(echo "$pids" | tr '\n' ' '))"
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 10); do
    [[ -z "$(worker_pids)" ]] && break
    sleep 1
  done
  pids="$(worker_pids)"
  if [[ -n "$pids" ]]; then
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi
  log "worker 已停止"
}

fix_frontend_perms() {
  local dist="$APP_DIR/frontend/dist"
  if [[ -d "$dist" ]]; then
    # Caddy 以 caddy 用户运行；若 scp 上传后目录是 700，会导致静态资源读不到、页面白屏
    chmod -R u=rwX,go=rX "$dist" 2>/dev/null || true
    log "已修正前端静态文件权限（dist -> 755/644）"
  fi
}

start_api() {
  [[ -x "$GUNICORN" ]] || die "找不到 gunicorn：$GUNICORN"
  cd "$BACKEND_DIR" || die "无法进入 $BACKEND_DIR"
  mkdir -p "$LOG_DIR"
  log "启动 API（gunicorn daemon，3 workers，127.0.0.1:$API_PORT）"
  "$GUNICORN" -c gunicorn_config.py app.main:app --daemon || die "gunicorn 启动失败，见 $LOG_DIR/error.log"

  for _ in $(seq 1 20); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then
      log "API 就绪"
      return 0
    fi
    sleep 1
  done
  die "API 20 秒内未就绪，请查看 $LOG_DIR/error.log"
}

start_worker() {
  [[ -x "$PYTHON" ]] || die "找不到 python：$PYTHON"
  cd "$BACKEND_DIR" || die "无法进入 $BACKEND_DIR"
  mkdir -p "$LOG_DIR"
  log "启动 worker（Redis 任务队列）"
  setsid nohup "$PYTHON" -m app.worker >> "$LOG_DIR/worker.log" 2>&1 < /dev/null &
  sleep 3
  if [[ -n "$(worker_pids)" ]]; then
    log "worker 就绪"
  else
    die "worker 启动失败，请查看 $LOG_DIR/worker.log"
  fi
}

status() {
  local ap wp
  ap="$(api_pids)"
  wp="$(worker_pids)"
  echo "---------------- 状态 ----------------"
  if [[ -n "$ap" ]]; then
    echo "API    : running (pids: $(echo "$ap" | tr '\n' ' '))"
  else
    echo "API    : stopped"
  fi
  if [[ -n "$wp" ]]; then
    echo "worker : running (pids: $(echo "$wp" | tr '\n' ' '))"
  else
    echo "worker : stopped"
  fi
  echo -n "health : "
  curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/health" 2>/dev/null || echo -n "不可用"
  echo
  echo -n "listen : "
  ss -tln 2>/dev/null | grep -q "127.0.0.1:$API_PORT" && echo "127.0.0.1:$API_PORT (仅本机)" || echo "未监听"
  echo "logs   : $LOG_DIR"
  echo "-------------------------------------"
}

case "${1:-restart}" in
  start)
    fix_frontend_perms
    start_api
    start_worker
    ;;
  stop)
    stop_worker
    stop_api
    ;;
  status)
    status
    exit 0
    ;;
  restart | *)
    fix_frontend_perms
    stop_worker
    stop_api
    start_api
    start_worker
    ;;
esac

status