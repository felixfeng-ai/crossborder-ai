# VeyaShip - Backend Production Dockerfile
# 多阶段构建：依赖层 → 运行时层
# 用于 docker-compose.prod.yml 构建生产镜像

# ════════════════════════════════════════════════════════════════
# 第一阶段：依赖安装
# ════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS deps

WORKDIR /app

# Python 优化：不生成 pyc 文件，不缓冲输出，不缓存 pip 包
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 安装系统级依赖（编译 PostgreSQL 驱动需要 gcc + libpq-dev）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 先拷 requirements.txt 再装依赖——利用 Docker 层缓存
# requirements.txt 不变时跳过 pip install，大幅加快构建速度
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ════════════════════════════════════════════════════════════════
# 第二阶段：运行镜像
# ════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS runtime

WORKDIR /app

# 从 deps 阶段复制已安装的 Python 包
# 只复制 site-packages，不复制构建时工具
COPY --from=deps /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=deps /usr/local/bin/ /usr/local/bin/

# 仅复制后端应用代码（.dockerignore 排除了 .env, __pycache__ 等）
COPY ./app /app/app
COPY ./migrations /app/migrations

# 创建非 root 用户运行应用（安全最佳实践）
RUN addgroup --system --gid 1001 app \
    && adduser --system --uid 1001 --ingroup app app \
    && mkdir -p /app/storage/images /app/storage/videos \
    && chown -R app:app /app

USER app

EXPOSE 8000

# 生产模式启动：无 --reload，自动从 .env 或环境变量读取配置
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
