#!/usr/bin/env bash
# VeyaShip 生产部署脚本：同步代码、构建前后端、执行迁移、重启并检查健康状态。
set -euo pipefail

REPO_ROOT="${VEYASHIP_REPO_ROOT:-/opt/veyaship}"
PROJECT_DIR="$REPO_ROOT/crossborder-ai"
WEB_ROOT="${VEYASHIP_WEB_ROOT:-/var/www/veyaship}"
SERVICE_NAME="${VEYASHIP_SERVICE_NAME:-veyaship-backend.service}"
ENV_FILE="$PROJECT_DIR/.env"

echo "===== VeyaShip 部署开始 $(date '+%F %T') ====="

# 生产密钥只在服务器生成并落盘，不进入仓库或 Actions 日志。
ensure_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    if ! grep -Eq "^${key}=.+$" "$ENV_FILE"; then
      sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    fi
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

ensure_random_env_secret() {
  local key="$1"
  if grep -Eq "^${key}=.+$" "$ENV_FILE" 2>/dev/null; then
    return
  fi
  local generated
  generated="$(openssl rand -base64 48)"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${generated}|" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$generated" >> "$ENV_FILE"
  fi
}

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

# 独立数据密钥用于新写入的敏感字段；旧 JWT 派生密文仍可回退解密。
ensure_random_env_secret "DATA_ENCRYPTION_KEY"

BACKUP_KEY_FILE="/etc/veyaship/backup.key"
install -d -m 700 /etc/veyaship
if [ ! -s "$BACKUP_KEY_FILE" ]; then
  (
    umask 077
    openssl rand -base64 48 > "$BACKUP_KEY_FILE"
  )
fi
chmod 600 "$BACKUP_KEY_FILE"
ensure_env_value "BACKUP_ENCRYPTION_KEY_FILE" "$BACKUP_KEY_FILE"
ensure_env_value "BACKUP_ENCRYPTION_REQUIRED" "1"

echo "[0/5] 生产加密密钥已就绪"

if [ "${VEYASHIP_SKIP_SYNC:-0}" = "1" ]; then
  echo "[1/5] 使用 GitHub Actions 上传的代码"
else
  cd "$REPO_ROOT"
  for attempt in 1 2 3 4 5; do
    if timeout 45s git -c http.version=HTTP/1.1 fetch origin main; then
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
fi

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
CURRENT_OUTPUT="$(./venv/bin/alembic current 2>/dev/null || true)"
if ! printf '%s\n' "$CURRENT_OUTPUT" | grep -Eq '[0-9]{3}_'; then
  HAS_BASELINE=$(
    ./venv/bin/python "$PROJECT_DIR/deploy/veyaship/check_schema_baseline.py"
  )
  if [ "$HAS_BASELINE" = "1" ]; then
    echo "检测到已有生产表但缺少 Alembic 版本，基线标记到 021"
    ./venv/bin/alembic stamp 021_marketing_video_projects
  fi
fi
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
