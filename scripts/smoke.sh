#!/usr/bin/env bash
# 冒烟测试：起一个临时实例，把主要接口跑一遍，不碰真实数据。
#
# 用法：
#   uv sync            # 首次或依赖变更后
#   bash scripts/smoke.sh
#
# 环境变量：
#   SMOKE_PORT  临时端口，默认 8099
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${SMOKE_PORT:-8099}"
BIN="$ROOT/.venv/bin/sentence-api"
TMP="$(mktemp -d)"
PID=""

cleanup() {
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

if [ ! -x "$BIN" ]; then
  echo "未找到 $BIN，先执行 uv sync" >&2
  exit 1
fi

cat > "$TMP/config.toml" <<TOML
[server]
host = "127.0.0.1"
port = ${PORT}

[database]
type = "sqlite"

[database.sqlite]
path = "${TMP}/sentences.db"
TOML

# 应用按当前目录找 config.toml，所以必须在这个目录里启动
cd "$TMP"
"$BIN" > "$TMP/server.log" 2>&1 &
PID=$!

BASE="http://127.0.0.1:${PORT}"
ready=0
for _ in $(seq 1 60); do
  if curl -sf "${BASE}/api/sentences?limit=1" > /dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "服务启动失败，日志：" >&2
    cat "$TMP/server.log" >&2
    exit 1
  fi
  sleep 0.25
done
if [ "$ready" != "1" ]; then
  echo "等待服务就绪超时，日志：" >&2
  cat "$TMP/server.log" >&2
  exit 1
fi

pass=0
fail=0
check() {
  local name="$1" expect="$2" actual="$3"
  if [ "$expect" = "$actual" ]; then
    pass=$((pass + 1))
    printf '  ✓ %s\n' "$name"
  else
    fail=$((fail + 1))
    printf '  ✗ %s（期望 %s，实际 %s）\n' "$name" "$expect" "$actual"
  fi
}

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "接口冒烟："

check "首页返回 200" 200 "$(code "${BASE}/")"
check "静态资源可访问" 200 "$(code "${BASE}/static/index.html")"
check "列表为空时 total=0" "0" \
  "$(curl -s "${BASE}/api/sentences?limit=1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["total"])')"

created="$(curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"hitokoto":"冒烟测试句子","author":"smoke","categories":["测试"]}' \
  "${BASE}/api/sentences")"
sid="$(printf '%s' "$created" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("id",""))')"
check "新增返回 id" "1" "$sid"
check "新增后 list 返回 200" 200 "$(code "${BASE}/api/sentences?limit=10")"
check "随机接口 200" 200 "$(code "${BASE}/api/random")"
check "按分类随机 200" 200 "$(code "${BASE}/api/random?category=%E6%B5%8B%E8%AF%95")"
check "分类列表 200" 200 "$(code "${BASE}/api/categories")"
check "导出 200" 200 "$(code "${BASE}/api/export")"
check "改一条 200" 200 "$(code -X PUT -H 'Content-Type: application/json' \
  -d '{"hitokoto":"改过的句子","author":"smoke","categories":["测试"],"commit_from":"smoke"}' \
  "${BASE}/api/sentences/${sid}")"
check "删一条 200" 200 "$(code -X DELETE "${BASE}/api/sentences/${sid}")"
check "删除后随机 404" 404 "$(code "${BASE}/api/random")"
check "非法新增返回 400" 400 "$(code -X POST -H 'Content-Type: application/json' \
  -d '{"hitokoto":"","author":""}' "${BASE}/api/sentences")"

echo
if [ "$fail" -gt 0 ]; then
  echo "✗ ${fail} 项失败（通过 ${pass} 项）"
  echo "服务日志："
  cat "$TMP/server.log"
  exit 1
fi
echo "✓ 全部 ${pass} 项通过"
