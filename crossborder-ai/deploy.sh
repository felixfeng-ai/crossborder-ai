#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# VeyaShip - 一键部署脚本
# ════════════════════════════════════════════════════════════════
# 用法：
#   chmod +x deploy.sh
#   sudo ./deploy.sh
#
# 前置条件：
#   - Ubuntu 22.04+ / Debian 12+
#   - 域名已指向本服务器 IP
#   - 已安装 git
# ════════════════════════════════════════════════════════════════

set -euo pipefail  # 出错立即停止，未定义变量报错

# ── 颜色 ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_step()  { echo -e "\n${GREEN}━━━ $1 ━━━${NC}"; }
print_info()  { echo -e "  ${YELLOW}→${NC} $1"; }
print_ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
print_err()   { echo -e "  ${RED}✗${NC} $1"; }

# ════════════════════════════════════════════════════════════════
# 第一步：环境检查
# ════════════════════════════════════════════════════════════════
print_step "环境检查"

# 检查是否以 root 运行（Docker 需要权限）
if [ "$EUID" -ne 0 ]; then
    print_err "请用 sudo 运行：sudo ./deploy.sh"
    exit 1
fi

# 检查操作系统
if [ ! -f /etc/os-release ]; then
    print_err "不支持的操作系统"
    exit 1
fi

. /etc/os-release
print_ok "系统：$ID $VERSION_ID"

# ════════════════════════════════════════════════════════════════
# 第二步：安装 Docker + Docker Compose
# ════════════════════════════════════════════════════════════════
print_step "安装 Docker"

if ! command -v docker &> /dev/null; then
    print_info "正在安装 Docker..."
    curl -fsSL https://get.docker.com | bash
    systemctl enable --now docker
    print_ok "Docker 安装完成"
else
    print_ok "Docker 已安装：$(docker --version)"
fi

if ! command -v docker compose &> /dev/null; then
    print_info "正在安装 Docker Compose..."
    apt-get update && apt-get install -y docker-compose-plugin
    print_ok "Docker Compose 安装完成"
else
    print_ok "Docker Compose 已安装"
fi

# ════════════════════════════════════════════════════════════════
# 第三步：克隆/更新代码
# ════════════════════════════════════════════════════════════════
print_step "获取代码"

PROJECT_DIR="/opt/veyaship"
if [ -d "$PROJECT_DIR" ]; then
    print_info "项目已存在，更新代码..."
    cd "$PROJECT_DIR"
    git pull
    print_ok "代码已更新"
else
    print_info "克隆项目代码..."
    # ← 替换为你的实际仓库地址
    git clone https://github.com/your-org/crossborder-ai.git "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    print_ok "代码已克隆"
fi

# ════════════════════════════════════════════════════════════════
# 第四步：创建 .env 文件
# ════════════════════════════════════════════════════════════════
print_step "环境变量"

if [ ! -f ".env" ]; then
    print_info "创建 .env 文件..."
    print_info "请编辑 $PROJECT_DIR/.env 填入实际配置后重新运行此脚本"
    cp .env.production .env

    # 生成随机密钥
    SECRET=$(openssl rand -hex 32)
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s/your-super-secret-key-change-in-production/$SECRET/" .env
    sed -i "s/your-jwt-secret-key-change-in-production/$JWT_SECRET/" .env

    print_err ".env 已创建，请编辑填入以下信息后重新运行："
    echo ""
    echo "  nano $PROJECT_DIR/.env"
    echo ""
    echo "  必须修改的字段："
    echo "    - APP_URL      → https://你的域名.com"
    echo "    - BACKEND_CORS_ORIGINS → [\"https://你的域名.com\"]"
    echo "    - POSTGRES_PASSWORD → 设置强密码"
    echo "    - DEEPSEEK_API_KEY  → 填入你的 DeepSeek Key"
    echo "    - REPLICATE_API_KEY → 填入你的 Replicate Key"
    echo "    - 将 example.com 替换为你的域名（nginx/nginx.conf 中）"
    echo ""
    exit 0
fi

print_ok ".env 已存在"

# ════════════════════════════════════════════════════════════════
# 第五步：SSL 证书（Let's Encrypt）
# ════════════════════════════════════════════════════════════════
print_step "SSL 证书"

DOMAIN=$(grep -oP 'server_name\s+\K[^;]+' nginx/nginx.conf | head -1 | awk '{print $1}')

if [ ! -d "nginx/ssl" ] || [ ! -f "nginx/ssl/cert.pem" ]; then
    print_info "申请 Let's Encrypt SSL 证书..."

    # 创建证书存放目录
    mkdir -p nginx/ssl nginx/www

    # 先启动 Nginx（仅 HTTP 模式，用于 Certbot 验证）
    print_info "启动临时 Nginx 进行域名验证..."
    docker compose -f docker-compose.prod.yml up -d nginx

    # 安装 Certbot
    if ! command -v certbot &> /dev/null; then
        apt-get update && apt-get install -y certbot
    fi

    # 申请证书（webroot 模式）
    certbot certonly --webroot -w nginx/www \
        -d "$DOMAIN" \
        -d "www.$DOMAIN" \
        --non-interactive \
        --agree-tos \
        --email admin@"$DOMAIN" \
        || true  # 失败不中断

    # 如果 certbot 成功，复制证书到 nginx 目录
    if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" nginx/ssl/cert.pem
        cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" nginx/ssl/key.pem
        print_ok "SSL 证书已获取"

        # 设置自动续期 cron
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /opt/veyaship/nginx/ssl/cert.pem && cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /opt/veyaship/nginx/ssl/key.pem && docker compose -f /opt/veyaship/docker-compose.prod.yml restart nginx") | crontab -
        print_ok "自动续期 cron 已设置"
    else
        print_err "SSL 证书申请失败，请手动配置证书到 nginx/ssl/ 目录"
        print_info "也可以先用 HTTP 模式部署，之后手动配置 HTTPS"
    fi
else
    print_ok "SSL 证书已存在"
fi

# ════════════════════════════════════════════════════════════════
# 第六步：启动服务
# ════════════════════════════════════════════════════════════════
print_step "启动服务"

# 停止旧容器（保留数据卷）
docker compose -f docker-compose.prod.yml down --remove-orphans

# 构建镜像并先启动数据库
print_info "构建镜像..."
docker compose -f docker-compose.prod.yml build

print_info "启动数据库..."
docker compose -f docker-compose.prod.yml up -d postgres qdrant

# 等待数据库就绪
print_info "等待 PostgreSQL 就绪..."
for i in $(seq 1 30); do
    if docker compose -f docker-compose.prod.yml exec -T postgres \
        pg_isready -U "${POSTGRES_USER:-crossborder}" -d "${POSTGRES_DB:-crossborder_ai}" > /dev/null 2>&1; then
        print_ok "PostgreSQL 就绪"
        break
    fi
    if [ "$i" -eq 30 ]; then
        print_err "PostgreSQL 未能在预期时间内就绪"
    fi
    sleep 2
done

# 迁移必须先于应用启动；失败时直接阻断发布，避免 schema 漂移。
print_step "数据库迁移"
docker compose -f docker-compose.prod.yml run --rm --no-deps backend alembic upgrade head

print_info "启动所有服务..."
docker compose -f docker-compose.prod.yml up -d
print_ok "所有服务已启动"

# ════════════════════════════════════════════════════════════════
# 第七步：健康检查
# ════════════════════════════════════════════════════════════════
print_step "健康检查"

sleep 10  # 等待服务启动

# 检查各服务状态
for service in postgres backend frontend nginx; do
    STATUS=$(docker compose -f docker-compose.prod.yml ps "$service" --format "{{.Status}}" 2>/dev/null || echo "unknown")
    if echo "$STATUS" | grep -q "Up\|healthy"; then
        print_ok "$service：$STATUS"
    else
        print_err "$service：$STATUS"
    fi
done

# 检查后端 API
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    print_ok "后端 API 健康检查通过"
else
    print_err "后端 API 未响应，查看日志：docker compose -f docker-compose.prod.yml logs backend"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  VeyaShip 部署完成！${NC}"
echo -e "${GREEN}  访问地址：https://$DOMAIN${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "常用命令："
echo "  查看日志：  docker compose -f docker-compose.prod.yml logs -f"
echo "  重启服务：  docker compose -f docker-compose.prod.yml restart"
echo "  停止服务：  docker compose -f docker-compose.prod.yml down"
echo "  更新代码：  git pull && docker compose -f docker-compose.prod.yml up -d --build"
echo ""
