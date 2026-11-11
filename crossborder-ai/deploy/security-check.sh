#!/usr/bin/env bash
# VeyaShip 生产安全核验：只输出检查结果，不输出任何密钥内容。
set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/veyaship/crossborder-ai/.env}"
FAILURES=0

fail() {
  echo "[FAIL] $*" >&2
  FAILURES=$((FAILURES + 1))
}

pass() {
  echo "[PASS] $*"
}

read_env() {
  local key="$1"
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1 | tr -d "\"'"
}

if [ ! -r "$ENV_FILE" ]; then
  echo "[FAIL] 无法读取环境文件：$ENV_FILE" >&2
  exit 1
fi

ENV_MODE="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo unknown)"
case "$ENV_MODE" in
  400|600) pass "环境文件权限为 $ENV_MODE" ;;
  *) fail "环境文件权限应为 600 或 400，当前为 $ENV_MODE" ;;
esac

DB_SSL_MODE_VALUE="$(read_env DB_SSL_MODE)"
case "$DB_SSL_MODE_VALUE" in
  verify-ca|verify-full) pass "PostgreSQL TLS 模式为 $DB_SSL_MODE_VALUE" ;;
  *) fail "DB_SSL_MODE 必须是 verify-ca 或 verify-full" ;;
esac

DB_SSL_CA_PATH_VALUE="$(read_env DB_SSL_CA_PATH)"
if [ -n "$DB_SSL_CA_PATH_VALUE" ] && [ -r "$DB_SSL_CA_PATH_VALUE" ]; then
  pass "PostgreSQL CA 文件可读"
else
  fail "DB_SSL_CA_PATH 未配置或文件不可读"
fi

DATA_KEY_VALUE="$(read_env DATA_ENCRYPTION_KEY)"
case "$DATA_KEY_VALUE" in
  ""|*replace*|*change*|*your-*)
    fail "DATA_ENCRYPTION_KEY 未配置或仍为占位值"
    ;;
  *)
    pass "独立数据加密密钥已配置"
    ;;
esac

BACKUP_KEY_FILE_VALUE="$(read_env BACKUP_ENCRYPTION_KEY_FILE)"
if [ -n "$BACKUP_KEY_FILE_VALUE" ] && [ -r "$BACKUP_KEY_FILE_VALUE" ]; then
  pass "备份加密密钥文件可读"
  KEY_MODE="$(stat -c '%a' "$BACKUP_KEY_FILE_VALUE" 2>/dev/null || echo unknown)"
  case "$KEY_MODE" in
    400|600) pass "备份密钥文件权限为 $KEY_MODE" ;;
    *) fail "备份密钥文件权限应为 600 或 400，当前为 $KEY_MODE" ;;
  esac
else
  fail "BACKUP_ENCRYPTION_KEY_FILE 未配置或文件不可读"
fi

AT_REST_EVIDENCE_VALUE="$(read_env AT_REST_ENCRYPTION_EVIDENCE)"
if [ -n "$AT_REST_EVIDENCE_VALUE" ] && [ -s "$AT_REST_EVIDENCE_VALUE" ]; then
  if grep -Eqi 'disk_encryption[=: ]+(kms|true|enabled)' "$AT_REST_EVIDENCE_VALUE" \
    && grep -Eqi 'object_storage_encryption[=: ]+(kms|sse|true|enabled)' "$AT_REST_EVIDENCE_VALUE"; then
    pass "云盘和对象存储静态加密证据完整"
  else
    fail "静态加密证据必须包含 disk_encryption 与 object_storage_encryption"
  fi
else
  fail "缺少 AT_REST_ENCRYPTION_EVIDENCE 证据文件"
fi

if command -v psql >/dev/null 2>&1; then
  PGHOST_VALUE="$(read_env PGHOST)"; PGHOST_VALUE="${PGHOST_VALUE:-$(read_env POSTGRES_SERVER)}"
  PGPORT_VALUE="$(read_env PGPORT)"; PGPORT_VALUE="${PGPORT_VALUE:-$(read_env POSTGRES_PORT)}"
  PGUSER_VALUE="$(read_env PGUSER)"; PGUSER_VALUE="${PGUSER_VALUE:-$(read_env POSTGRES_USER)}"
  PGDATABASE_VALUE="$(read_env POSTGRES_DB)"
  PGPASSWORD_VALUE="$(read_env PGPASSWORD)"; PGPASSWORD_VALUE="${PGPASSWORD_VALUE:-$(read_env POSTGRES_PASSWORD)}"

  SSL_STATUS="$(
    PGPASSWORD="$PGPASSWORD_VALUE" PGSSLMODE="$DB_SSL_MODE_VALUE" \
      psql -h "$PGHOST_VALUE" -p "$PGPORT_VALUE" -U "$PGUSER_VALUE" \
      -d "$PGDATABASE_VALUE" -Atqc "SHOW ssl" 2>/dev/null || true
  )"
  if [ "$SSL_STATUS" = "on" ]; then
    pass "PostgreSQL 服务端已开启 TLS"
  else
    fail "PostgreSQL 服务端 TLS 未开启或无法连接"
  fi
else
  fail "找不到 psql，无法验证 PostgreSQL 服务端 TLS"
fi

if [ "$FAILURES" -gt 0 ]; then
  echo "[security-check] 失败项：$FAILURES" >&2
  exit 1
fi

echo "[security-check] 全部安全检查通过"
