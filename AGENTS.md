# AGENTS.md — sentence_api 标准工作流

本文件定义本仓库改动、验证、打包与发布的固定流程，供 AI Agent 与开发者共同遵循。
核心顺序：**改 → 验 → 打包 → 提交并推送 → 发版**。

---

## 0. 前置检查

动手前先确认工作区状态，避免把无关改动混进提交：

```bash
git status --short
git branch --show-current
git tag --sort=-v:refname | head -3   # 确认当前最新的已发布版本
```

- 有与本次无关的未跟踪文件时，先移出工作区或加进 `.gitignore`，不要 `git add .`
- `data/`、`*.db`、`.venv/`、`dist/` 都已在 `.gitignore` 中，正常不会出现

---

## 1. 改动

### 1.1 改路径相关逻辑前必须知道的事

**配置是按「当前工作目录」查找的**，`config.load_config()` 只认 `config/config.toml`
或 `config.toml`，代码里没有环境变量可覆盖。两种运行方式依赖不同的工作目录：

| 运行方式 | 工作目录 | 配置实际位置 |
|----------|----------|--------------|
| systemd / 源码运行 | 项目根目录 | `<项目>/config/config.toml` |
| Docker | `/data` | `/data/config/config.toml` |

SQLite 路径同理：默认相对当前目录，容器镜像里写成绝对路径 `/data/sentences.db`。
静态文件用 `Path(__file__).parent` 定位，不受工作目录影响。

改动配置、数据库路径、启动入口时，**两种运行方式都要能跑**。

### 1.2 修改原则

- **最小改动**：只改与问题直接相关的代码，不顺带重构
- **保持风格**：现有代码是 `from __future__` 风格之外的普通 Python 3.12，4 空格缩进，中文注释与错误文案
- **不新增依赖**：`psycopg2-binary` 已是必装项（即使默认用 SQLite），新增依赖要先改 `pyproject.toml` 并 `uv lock`
- **数据库语句**：`database.py` 用 `{ph}` 占位符 + `_sql()` 适配 SQLite/PostgreSQL，新写 SQL 必须沿用这个模式，不要硬编码 `?` 或 `%s`

### 1.3 安全底线

- 本服务**没有任何鉴权**，增删改与导入接口对能访问到的人全开放
- 新增接口时不要假设存在登录态；文档与 compose 里应保持"默认只绑回环"的取向
- 涉及外部可访问的默认值时，宁可保守

---

## 2. 验证

本项目没有单元测试套件，验证以「导入检查 + 冒烟脚本 + 手工点查」为主。

### 2.1 静态校验

```bash
uv sync
uv run python -c "import sentence_api.main"
```

### 2.2 冒烟测试（每次改动必跑）

```bash
bash scripts/smoke.sh
```

脚本会在临时目录起一个独立实例（临时配置、临时 SQLite、随机端口），不触碰真实数据，
覆盖 13 项：首页、静态资源、空列表、新增、列表、随机、按分类随机、分类列表、导出、
修改、删除、删除后 404、非法参数 400。

- 全绿才算通过；失败时会打印服务日志
- 改了接口行为却没同步脚本时，先判断是脚本过时还是代码回归

### 2.3 手工验证（涉及前端或交互时）

```bash
uv run sentence-api          # 默认 http://127.0.0.1:8000
```

浏览器打开首页，按改动点操作一遍：新增句子、改分类、导入导出、移动端宽度下的卡片布局。

---

## 3. 打包

```bash
uv build
ls dist/
```

产物：`dist/sentence_api-<version>-py3-none-any.whl` 与 sdist。
安装方式变化时，确认 wheel 里带上了 `src/sentence_api/static/`（`pyproject.toml`
的 `include` 负责）。

---

## 4. 提交并推送

### 4.1 确认变更范围

```bash
git status --short
git diff --stat
```

只暂存本次涉及的文件，禁止 `git add .`。

### 4.2 提交信息

格式：`type(scope): 主题`，正文说明原因与影响。

| 类型 | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修缺陷 |
| `build` | 构建、镜像、依赖 |
| `docs` | 文档 |
| `refactor` | 不改变行为的重构 |
| `chore` | 杂项 |

```bash
git commit -m "fix(api): 随机接口在分类为空时返回 404"
git push origin main
```

---

## 5. 版本发布

### 5.1 版本号规则（0.x 阶段）

- 破坏性变更或大功能：升次版本号（`0.1.x → 0.2.0`）
- 其余（缺陷修复、部署方式、文档）：升补丁位（`0.1.3 → 0.1.4`）

### 5.2 版本号只有一处

```bash
grep -rn "version = " pyproject.toml
```

只需要改 `pyproject.toml` 的 `[project].version`，仓库里没有其它硬编码版本号
（`src/sentence_api/__init__.py` 也没有版本常量）。改完重新锁定一次：

```bash
uv lock
grep -A1 'name = "sentence-api"' uv.lock | head -2   # 应显示新版本
```

### 5.3 提交并打 tag

```bash
git add pyproject.toml uv.lock
git commit -m "release v<新版本>: <简述>"
git tag -a v<新版本> -m "v<新版本>"
git push origin main
git push origin v<新版本>
```

标签一经推送**不要移动**。发现打错时，发下一个补丁版本，而不是 `tag -f` 覆盖。

### 5.4 GitHub Release

```bash
gh release create v<新版本> --title "v<新版本>" --notes-file <(git log -1 --format=%b) \
  dist/sentence_api-<新版本>-py3-none-any.whl dist/sentence_api-<新版本>.tar.gz
```

### 5.5 Docker 镜像

推 `v*` 标签或更新 `main` 会触发 `.github/workflows/docker.yml`，构建
`linux/amd64` 与 `linux/arm64` 镜像并推送到 `ghcr.io/<owner>/sentence-api`，
标签与 git tag 同名。PR 只构建不推送。

镜像里的依赖按 `uv.lock` 安装（`uv sync --frozen --no-editable`），与本地锁定版本一致。

---

## 6. 部署方式对照

| | systemd | Docker |
|---|---|---|
| 入口 | `sentence-api`（`WorkingDirectory` 指项目根） | 容器 `CMD sentence-api`（`WORKDIR /data`） |
| 配置 | `<项目>/config/config.toml` | `/data/config/config.toml`（首次启动自动生成） |
| 数据库 | 项目目录下的 `sentences.db` | `/data/sentences.db` |
| 权限 | 由 `User=` 指定 | 默认跟随 `/data` 属主，可用 `PUID`/`PGID` 覆盖 |
| 端口修改 | 改配置里的 `server.port` | 改配置 + `docker-compose.yml` 的端口映射 |

---

## 快速检查清单

**日常改动**
- [ ] `git status` 干净或仅有本次相关改动
- [ ] `uv run python -c "import sentence_api.main"` 通过
- [ ] `bash scripts/smoke.sh` 全绿
- [ ] 只暂存相关文件，commit message 说明原因

**发布**
- [ ] `pyproject.toml` 版本号已改，`uv lock` 已同步
- [ ] `uv build` 产物在 `dist/`
- [ ] commit + tag 已推送，tag 未覆盖历史
- [ ] GitHub Release 附带 wheel 与 sdist
- [ ] Actions 镜像构建通过，`docker pull` 能拿到新标签
