#!/usr/bin/env bash
# ============================================================
# veyaship.com —— 香港反向代理上线脚本（nginx + certbot）
#
# 架构：
#   浏览器 → https://veyaship.com (香港 43.129.23.197, 已签证书)
#          → https://47.116.138.61 (阿里云, 原 VeyaShip 站点)
#
# 为什么要反代：阿里云对 veyaship.com 有备案拦截。
# 经实测，拦截发生在 TLS SNI 层（而非 HTTP Host 层）：
#   SNI=veyaship.com          → 连接被重置（code 000）
#   SNI 空 + Host=veyaship.com → 200，正常返回 VeyaShip
#   走 80 明文 + Host=域名     → 403 阿里云 Non-compliant 页
# 因此上游必须用「IP 建连 + 不发 SNI + 走 https」，
# 同时 Host 头保持真实域名，后端 request.base_url 才能拼出正确回调地址。
#
# 前置条件：DNS 已把 veyaship.com / www.veyaship.com 解析到 43.129.23.197
# 执行方式：在 HK 上以 ubuntu 身份执行 —— bash deploy-nginx.sh
# 幂等：可重复执行，会覆盖同名 vhost 与缓存配置
# ============================================================
set -e

DOMAIN=veyaship.com
UPSTREAM=47.116.138.61
SRV=/etc/nginx/sites-available/$DOMAIN
ENL=/etc/nginx/sites-enabled/$DOMAIN
CACHE_CONF=/etc/nginx/conf.d/veyaship-cache.conf

echo "==> 阶段0：准备静态资源缓存目录"
# proxy_cache_path 只能写在 http 上下文，站点文件里放不了，故单独走 conf.d
sudo mkdir -p /var/cache/nginx/veyaship
sudo chown -R www-data:www-data /var/cache/nginx

echo "==> 阶段1：仅 80 端口（供 ACME 验证）"
sudo mkdir -p /var/www/html
sudo tee $SRV >/dev/null <<NGINX
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://\$host\$request_uri; }
}
NGINX
sudo ln -sf $SRV $ENL
sudo nginx -t && sudo systemctl reload nginx
echo "phase1 ok"

echo "==> 阶段2：certbot 签证书（HTTP-01）"
sudo certbot certonly --webroot -w /var/www/html \
  -d $DOMAIN -d www.$DOMAIN \
  --non-interactive --agree-tos --email admin@$DOMAIN --no-eff-email
echo "cert ok"

echo "==> 阶段3：缓存区声明"
sudo tee $CACHE_CONF >/dev/null <<NGINX
# veyaship.com 静态资源边缘缓存
# 前端产物文件名带内容 hash 且响应头是 immutable，可安全长缓存。
proxy_cache_path /var/cache/nginx/veyaship levels=1:2
                 keys_zone=veyaship_static:10m
                 max_size=1g inactive=30d use_temp_path=off;
NGINX

echo "==> 阶段4：完整反代配置（80 + 443）"
sudo tee $SRV >/dev/null <<NGINX
# veyaship.com —— 香港反代到阿里云
#
# 关键点：
#   1) proxy_pass 写 IP   → 上游建连时不发 SNI，绕过备案拦截
#   2) Host 头写真实域名  → 后端 request.base_url 拼出 https://veyaship.com，OAuth 回调正确
#   3) Agent API 定向关闭缓冲 → SSE 必须直通，其他页面和静态资源保持 Nginx 正常缓冲
#   4) gzip_proxied any    → 系统 nginx.conf 里 gzip_types/gzip_proxied 是注释掉的，
#                            默认只压 text/html 且不压反代响应，等于 1MB 前端产物裸传
#   5) /assets/ 走边缘缓存 → 香港→上海 RTT 165ms，静态产物复用后不必回源
#
# 连接池：keepalive 复用长连接，避免每个请求重新握手（0.3~0.8s 且抖动大）。
upstream veyaship_origin {
    server $UPSTREAM:443;
    keepalive 32;
    keepalive_timeout 60s;
}

server {
    listen 443 ssl http2;
    server_name $DOMAIN www.$DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    # 跨境链路 RTT 高，复用会话可省掉重复的完整握手
    ssl_session_cache   shared:veyaship_ssl:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets on;

    client_max_body_size 50m;   # CSV 批量上传

    gzip on;
    gzip_proxied any;           # 关键：不加这行，反代响应一律不压缩
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_vary on;
    gzip_types text/plain text/css application/javascript application/json
               application/xml image/svg+xml;

    # 带 hash 的构建产物：边缘缓存，命中后不回源
    location /assets/ {
        proxy_pass https://veyaship_origin;
        proxy_http_version 1.1;
        proxy_set_header Connection        "";
        proxy_set_header Host              \$host;
        proxy_set_header X-Forwarded-For   \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_ssl_server_name off;
        proxy_ssl_verify      off;

        proxy_cache            veyaship_static;
        proxy_cache_valid      200 30d;
        proxy_cache_use_stale  error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_lock       on;
        proxy_cache_background_update on;
        add_header X-Cache-Status \$upstream_cache_status always;
    }

    # 字体文件稳定且首屏会预加载，命中边缘缓存后不再回源上海。
    location /fonts/ {
        proxy_pass https://veyaship_origin;
        proxy_http_version 1.1;
        proxy_set_header Connection        "";
        proxy_set_header Host              \$host;
        proxy_set_header X-Forwarded-For   \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_ssl_server_name off;
        proxy_ssl_verify      off;

        proxy_cache            veyaship_static;
        proxy_cache_valid      200 7d;
        proxy_cache_use_stale  error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_lock       on;
        proxy_cache_background_update on;
        proxy_ignore_headers Cache-Control Expires Set-Cookie;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "public, max-age=604800" always;
        add_header X-Cache-Status \$upstream_cache_status always;
    }

    # 首页演示媒体不在首屏，浏览器端已经 lazy-load，边缘侧再做 7 天缓存。
    location /demo/ {
        proxy_pass https://veyaship_origin;
        proxy_http_version 1.1;
        proxy_set_header Connection        "";
        proxy_set_header Host              \$host;
        proxy_set_header X-Forwarded-For   \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_ssl_server_name off;
        proxy_ssl_verify      off;

        proxy_cache            veyaship_static;
        proxy_cache_valid      200 7d;
        proxy_cache_use_stale  error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_lock       on;
        proxy_cache_background_update on;
        proxy_ignore_headers Cache-Control Expires Set-Cookie;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "public, max-age=604800" always;
        add_header X-Cache-Status \$upstream_cache_status always;
    }

    # API 响应是动态业务数据，必须绕开 SPA 的短缓存。
    location ^~ /api/ {
        proxy_pass https://veyaship_origin;
        proxy_http_version 1.1;
        proxy_set_header Connection        "";
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host  \$host;
        proxy_ssl_server_name off;
        proxy_ssl_verify      off;

        proxy_buffering on;
        proxy_cache     off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # 健康检查保持实时，避免状态异常时仍命中旧的成功结果。
    location = /health {
        proxy_pass https://veyaship_origin;
        proxy_http_version 1.1;
        proxy_set_header Connection        "";
        proxy_set_header Host              \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_ssl_server_name off;
        proxy_ssl_verify      off;
        proxy_cache           off;
    }

    # 只有 Agent 任务流需要关闭缓冲，避免影响 HTML、字体和演示资源下载。
    location ^~ /api/v1/agent/ {
        proxy_pass https://veyaship_origin;
        proxy_http_version 1.1;
        proxy_set_header Connection        "";
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host  \$host;
        proxy_ssl_server_name off;
        proxy_ssl_verify      off;

        proxy_buffering off;
        proxy_cache     off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location / {
        proxy_pass https://veyaship_origin;
        proxy_http_version 1.1;
        # 清空 Connection 头是启用 upstream keepalive 的必要条件；
        # Agent SSE 已由上方独立 location 直通，这里只承载 SPA 与公开页面。
        proxy_set_header Connection        "";

        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        # 用 \$remote_addr 而非 \$proxy_add_x_forwarded_for：后端限流取 XFF 第一段，
        # 若保留客户端自带的 XFF，伪造一个就能把真实 IP 挤到第二位绕过限流。
        proxy_set_header X-Forwarded-For   \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host  \$host;

        # 上游按 IP 建连：不发 SNI、不校验证书
        proxy_ssl_server_name off;
        proxy_ssl_verify      off;

        proxy_buffering on;
        # SPA HTML 与公开页面内容很短且部署后无需实时变更，边缘缓存 30 秒吸收跨境回源抖动。
        proxy_cache            veyaship_static;
        proxy_cache_valid      200 30s;
        proxy_cache_use_stale  error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_lock       on;
        proxy_cache_background_update on;
        proxy_ignore_headers Cache-Control Expires Set-Cookie;
        add_header X-Cache-Status \$upstream_cache_status always;

        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}

server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://\$host\$request_uri; }
}
NGINX
sudo nginx -t && sudo systemctl reload nginx
echo "NGINX_DONE"
