#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# VeyaShip - 数据库自动备份脚本
# ════════════════════════════════════════════════════════════════
# 生产（阿里云 ECS）：PostgreSQL 16（systemd 原生，非 docker）
# 本地开发：SQLite 文件 crossborder_ai.db
#
# 用法：
#   手动：  sudo ./deploy/backup.sh
#   定时：  加到 crontab（生产环境每天 2:00，避开应用高峰）：
#           0 2 * * * /opt/veyaship/crossborder-ai/deploy/backup.sh >> /var/log/veyaship-backup.log 2>&1
#
# 可配置环境变量（都有默认值）：
#   BACKUP_DIR      备份存放目录（默认 /opt/veyaship/backups）
#   RETENTION_DAYS  保留天数，删除更早的备份（默认 7）
#   ENV_FILE        项目 .env 路径（用于读取 POSTGRES_* 凭据）
#   BACKUP_REMOTE   可选：rclone remote:path，设置了就多拷一份异地（强烈建议）
# ════════════════════════════════════════════════════════════════

set -euo pipefail

# ── 配置（可用环境变量覆盖） ──────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/opt/veyaship/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
ENV_FILE="${ENV_FILE:-/opt/veyaship/crossborder-ai/.env}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
BACKUP_ENCRYPTION_KEY_FILE="${BACKUP_ENCRYPTION_KEY_FILE:-}"
BACKUP_ENCRYPTION_REQUIRED="${BACKUP_ENCRYPTION_REQUIRED:-0}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── 从 .env 读取数据库凭据 ────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi
PGHOST="${PGHOST:-${POSTGRES_SERVER:-localhost}}"
PGPORT="${PGPORT:-${POSTGRES_PORT:-5432}}"
PGUSER="${PGUSER:-${POSTGRES_USER:-crossborder}}"
PGDB="${PGDB:-${POSTGRES_DB:-crossborder_ai}}"
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
export PGPASSWORD

ENCRYPT_SUFFIX=""
if [ -n "$BACKUP_ENCRYPTION_KEY_FILE" ]; then
  if [ ! -r "$BACKUP_ENCRYPTION_KEY_FILE" ]; then
    echo "[backup] 备份加密密钥文件不可读：$BACKUP_ENCRYPTION_KEY_FILE" >&2
    exit 1
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    echo "[backup] 找不到 openssl，无法执行备份加密" >&2
    exit 1
  fi
  ENCRYPT_SUFFIX=".enc"
elif [ "$BACKUP_ENCRYPTION_REQUIRED" = "1" ]; then
  echo "[backup] 已要求加密备份，但未配置 BACKUP_ENCRYPTION_KEY_FILE" >&2
  exit 1
fi

encrypt_stream() {
  if [ -n "$ENCRYPT_SUFFIX" ]; then
    openssl enc -aes-256-cbc -salt -pbkdf2 \
      -pass "file:$BACKUP_ENCRYPTION_KEY_FILE"
  else
    cat
  fi
}

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"

# ════════════════════════════════════════════════════════════════
# 1. 选择备份方式：PostgreSQL 优先，SQLite 兜底
# ════════════════════════════════════════════════════════════════
BACKED_UP=0

# ── PostgreSQL（生产） ───────────────────────────────────────
if command -v pg_dump >/dev/null 2>&1 && pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; then
  OUT="$BACKUP_DIR/veyaship_pg_$STAMP.dump.gz$ENCRYPT_SUFFIX"
  echo "[backup] 检测到 PostgreSQL，开始备份 $PGDB@$PGHOST ..."
  # -Fc = 自定义格式（压缩、可 pg_restore 选择性恢复）
  pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDB" -Fc \
    | gzip \
    | encrypt_stream > "$OUT"
  echo "[backup] PostgreSQL 备份完成：$OUT"
  BACKED_UP=1

# ── SQLite（本地开发） ───────────────────────────────────────
elif [ -f "$PROJECT_ROOT/backend/crossborder_ai.db" ]; then
  DB_FILE="$PROJECT_ROOT/backend/crossborder_ai.db"
  OUT="$BACKUP_DIR/veyaship_sqlite_$STAMP.db.gz$ENCRYPT_SUFFIX"
  echo "[backup] 检测到 SQLite，开始备份 $DB_FILE ..."
  # Windows (Git Bash/MSYS) 下把 POSIX 路径转成 Windows 路径，Linux 服务器原样
  if uname -s 2>/dev/null | grep -qi "MINGW\|MSYS"; then
    PY_DB_FILE="$(cygpath -w "$DB_FILE" 2>/dev/null || echo "$DB_FILE")"
    PY_OUT_TMP="$(cygpath -w "$OUT.tmp" 2>/dev/null || echo "$OUT.tmp")"
  else
    PY_DB_FILE="$DB_FILE"
    PY_OUT_TMP="$OUT.tmp"
  fi
  # 用 Python sqlite3 的 backup API（WAL 模式下也安全，保证一致性）
  PY_DB_FILE="$PY_DB_FILE" PY_OUT_TMP="$PY_OUT_TMP" python -c "
import os, sqlite3
src, dst = os.environ['PY_DB_FILE'], os.environ['PY_OUT_TMP']
con = sqlite3.connect(src)
b = sqlite3.connect(dst)
con.backup(b)
b.close(); con.close()
print('[backup] sqlite backup ok')
"
  if ! gzip -c "$OUT.tmp" | encrypt_stream > "$OUT"; then
    rm -f "$OUT.tmp"
    echo "[backup] SQLite 备份加密失败" >&2
    exit 1
  fi
  rm -f "$OUT.tmp"
  echo "[backup] SQLite 备份完成：$OUT"
  BACKED_UP=1
fi

if [ "$BACKED_UP" -eq 0 ]; then
  echo "[backup] 未找到可备份的数据库（无 pg 且无 sqlite）" >&2
  exit 1
fi

if [ -n "$ENCRYPT_SUFFIX" ]; then
  echo "[backup] 备份已使用 AES-256 加密"
else
  echo "[backup] 警告：本次备份未加密，生产环境必须启用 BACKUP_ENCRYPTION_KEY_FILE" >&2
fi

# ════════════════════════════════════════════════════════════════
# 2. 可选：异地副本（强烈建议生产开启）
#    先在服务器装 rclone，配置远端（如 OSS/S3/另一台机器），
#    然后 BACKUP_REMOTE='oss:veyaship-backup' ./deploy/backup.sh
# ════════════════════════════════════════════════════════════════
if [ -n "$BACKUP_REMOTE" ]; then
  if command -v rclone >/dev/null 2>&1; then
    rclone copy "$OUT" "$BACKUP_REMOTE/" && echo "[backup] 已同步异地副本：$BACKUP_REMOTE"
  else
    echo "[backup] 警告：BACKUP_REMOTE 已设置但未安装 rclone，跳过异地备份" >&2
  fi
fi

# ════════════════════════════════════════════════════════════════
# 3. 保留策略：删除 N 天前的旧备份
# ════════════════════════════════════════════════════════════════
DELETED=$(find "$BACKUP_DIR" -name "veyaship_*" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
echo "[backup] 保留策略：删除 $RETENTION_DAYS 天前的旧备份（本次清理 $DELETED 个）"

echo "[backup] 备份目录最近文件："
ls -lh "$BACKUP_DIR" | tail -5
