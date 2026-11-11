#!/usr/bin/env bash
# VeyaShip 生产部署脚本：同步代码、构建前后端、执行迁移、重启并检查健康状态。
set -euo pipefail

REPO_ROOT="${VEYASHIP_REPO_ROOT:-/opt/veyaship}"
PROJECT_DIR="$REPO_ROOT/crossborder-ai"
WEB_ROOT="${VEYASHIP_WEB_ROOT:-/var/www/veyaship}"
SERVICE_NAME="${VEYASHIP_SERVICE_NAME:-veyaship-backend.service}"

echo "===== VeyaShip 部署开始 $(date '+%F %T') ====="

cd "$REPO_ROOT"
for attempt in 1 2 3 4 5; do
  if git fetch origin main; then
    git reset --hard origin/main
    echo "[1/5] 代码已同步到 $(git log --oneline -1)"
    break
  fi
  echo "[1/5] git fetch 失败（第 ${attempt} 次），5 秒后重试..."
  sleep 5
  if [ "$attempt" -eq 5 ]; then
    echo "git fetch 连续 5 次失败，终止部署"
    exit 1
  fi
done

cd "$PROJECT_DIR/backend"
./venv/bin/pip install -q -r requirements.txt
echo "[2/5] 后端依赖就绪"

cd "$PROJECT_DIR/frontend"
npm ci --no-audit --no-fund
npm run build
rm -rf "$WEB_ROOT"/*
cp -r dist/* "$WEB_ROOT/"
echo "[3/5] 前端已发布到 $WEB_ROOT"

# 迁移失败必须阻断发布，不能再 stamp head 掩盖 schema 漂移。
cd "$PROJECT_DIR/backend"
./venv/bin/alembic upgrade head
./venv/bin/alembic current
echo "[4/5] 数据库迁移已到 head"

systemctl restart "$SERVICE_NAME"
for attempt in $(seq 1 12); do
  sleep 10
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "[5/5] 后端健康检查通过"
    echo "===== 部署完成 ====="
    exit 0
  fi
  echo "[5/5] 等待后端就绪... $((attempt * 10))s"
done

echo "后端 120s 内未就绪，部署失败"
exit 1
