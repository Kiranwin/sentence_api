# syntax=docker/dockerfile:1
#
# 轻量句子 API 容器镜像
#   - 依赖按 uv.lock 安装，镜像里的版本与仓库锁定的一致
#   - 非 root 运行；数据在 /data（config/config.toml + sentences.db）
#   - 首次启动自动生成默认配置（sqlite，监听 0.0.0.0:8000）
#
# ── 构建阶段 ──
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# 钉住构建工具版本，避免 uv 自身漂移
RUN pip install --no-cache-dir uv==0.13.7

WORKDIR /app

# 先只装第三方依赖，改源码不会让这一层缓存失效
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable

COPY src ./src
# --no-editable：装成完整副本，运行阶段不需要源码目录
RUN uv sync --frozen --no-dev --no-editable

# ── 运行阶段 ──
FROM python:3.12-slim

ARG TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=${TZ} \
    PATH="/app/.venv/bin:$PATH"

# tzdata 用于本地时间显示；gosu 用于按 PUID/PGID 降权
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata gosu \
    && rm -rf /var/lib/apt/lists/*

# 应用读取「当前目录」下的 config/config.toml，把工作目录放在数据卷里
WORKDIR /data

COPY --from=builder /app/.venv /app/.venv
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 0755 /usr/local/bin/entrypoint.sh \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /data \
    && chown -R app:app /app /data

# 不写 USER：以 root 启动，由 entrypoint 按 PUID/PGID 降权
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/sentences?limit=1', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["sentence-api"]
