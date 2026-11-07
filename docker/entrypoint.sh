#!/bin/sh
# 容器入口：按 PUID/PGID 降权、首次启动生成 /data/config/config.toml
set -e

DATA_DIR="${DATA_DIR:-/data}"
CONFIG_DIR="${DATA_DIR}/config"
CONFIG="${CONFIG_DIR}/config.toml"

mkdir -p "$DATA_DIR"

# 没指定 PUID/PGID 时跟随数据目录属主，宿主机什么都不用配
if [ -z "${PUID:-}" ] || [ -z "${PGID:-}" ]; then
    owner_uid="$(stat -c %u "$DATA_DIR")"
    owner_gid="$(stat -c %g "$DATA_DIR")"
    if [ "$owner_uid" = "0" ]; then
        owner_uid=1000
        owner_gid=1000
    fi
    PUID="${PUID:-$owner_uid}"
    PGID="${PGID:-$owner_gid}"
fi

# 以 root 启动时先调整运行用户，再用同一脚本重入，之后所有文件都归目标用户
if [ "$(id -u)" = "0" ]; then
    if [ "$PUID" != "0" ]; then
        if [ "$(id -g app)" != "$PGID" ]; then
            groupmod -o -g "$PGID" app
        fi
        if [ "$(id -u app)" != "$PUID" ]; then
            usermod -o -u "$PUID" app
        fi
        if [ "$(stat -c %u "$DATA_DIR")" != "$PUID" ] || [ "$(stat -c %g "$DATA_DIR")" != "$PGID" ]; then
            echo "[entrypoint] 调整数据目录属主为 ${PUID}:${PGID}"
            chown -R "$PUID:$PGID" "$DATA_DIR"
        fi
        exec gosu app "$0" "$@"
    fi
    echo "[entrypoint] PUID=0，以 root 运行，写出的文件在宿主机上属主为 root"
fi

if [ ! -w "$DATA_DIR" ]; then
    echo "[entrypoint] 数据目录不可写：${DATA_DIR}" >&2
    echo "[entrypoint] 在 compose 里设置 PUID/PGID 为宿主机目录的属主，或调整目录权限" >&2
    exit 1
fi

if [ ! -f "$CONFIG" ]; then
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG" <<'TOML'
# 轻量句子 API 容器配置（首次启动自动生成）
# 改完重启容器生效；端口改了记得同步 compose 的映射

[server]
# 容器内要监听 0.0.0.0，否则端口映射访问不到
host = "0.0.0.0"
port = 8000

[database]
# 当前仅支持 SQLite
type = "sqlite"

[database.sqlite]
path = "/data/sentences.db"
TOML
    echo "[entrypoint] 已生成默认配置 ${CONFIG}"
else
    echo "[entrypoint] 使用已有配置 ${CONFIG}"
fi

exec "$@"
