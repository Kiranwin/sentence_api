# 📖 轻量句子 API · 多分类一言风格服务

一个轻量、个人使用的句子服务，类似 [hitokoto](https://hitokoto.cn)（一言）。  
支持多分类、随机获取、网页管理、导入导出，并可通过 systemd 实现开机自启。

## ✨ 特性

- 🗄️ **轻量后端**：FastAPI + SQLite，资源占用极小
- 🏷️ **多分类支持**：一句话可属于多个分类（如"励志"、"古风"）
- 🖥️ **网页管理界面**：美观的卡片式 UI，支持句子增删改查、分类管理、导入导出
- 🔌 **API 接口**：符合 RESTful 风格，支持按分类随机获取句子
- 📂 **数据导入/导出**：JSON 格式，便于迁移、备份
- 📦 **单命令启动**：安装后直接运行 `sentence-api` 即可
- 🐧 **Linux 服务**：提供 systemd 配置，实现开机自启和进程守护

## 🛠️ 技术栈

| 角色       | 技术                                 |
| ---------- | ------------------------------------ |
| 后端框架   | FastAPI                              |
| 数据库     | SQLite3                              |
| 前端       | 原生 HTML / CSS / JavaScript         |
| 构建工具   | [uv](https://docs.astral.sh/uv/)     |
| 部署       | Uvicorn + systemd（Linux）           |

## 📦 安装

### 前提

- Python >= 3.12
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理 Python 与依赖

### 方式一：pip 安装（推荐）

```bash
# 从本地 wheel 安装
pip install dist/sentence_api-*.whl

# 启动服务
sentence-api
```

### 方式二：源码运行

```bash
git clone <repo-url>
cd sentence_api
uv sync
uv run sentence-api
```

### 方式三：使用虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate     # Linux/macOS
.venv\Scripts\activate        # Windows
pip install fastapi uvicorn python-multipart jinja2
uvicorn sentence_api.main:app --host 0.0.0.0 --port 8000
```

### 构建分发包

```bash
uv build
# 产物在 dist/ 目录下
```

## ⚙️ 配置

配置文件位于项目目录下的 `config/config.toml`（优先）或 `config.toml`（兼容）。  
参考 `config/config.example.toml` 创建：

```toml
[server]
host = "0.0.0.0"
port = 8000

[database]
# 当前仅支持 SQLite
type = "sqlite"

[database.sqlite]
path = "sentences.db"    # SQLite 文件路径

```

不创建配置文件则默认使用 SQLite + `sentences.db`。

## 🚀 启动服务

### 使用 CLI 命令（安装后）

```bash
sentence-api
```

### 开发模式（带自动重载）

```bash
uvicorn sentence_api.main:app --reload --host 0.0.0.0 --port 8000
```

### 生产模式（后台运行）

```bash
nohup sentence-api > uvicorn.log 2>&1 &
```

浏览器打开 `http://你的服务器IP:8000` 即可使用 Web 管理界面。

### API 文档

服务启动后 FastAPI 自动生成交互式文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 🐳 Docker 部署

适合放到 Linux 主机或 NAS 上常驻。镜像由 GitHub Actions 构建，当前发布
`linux/amd64`；ARM 设备建议改用 wheel 或源码运行。

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f
```

浏览器打开 `http://localhost:8000`。首次启动会在 `data/config/config.toml`
生成默认配置（SQLite，监听 `0.0.0.0:8000`）。

数据全在 `./data`，Compose 使用目录绑定（`./data:/data`），不是命名卷；
备份拷走该目录即可：

| 路径 | 内容 |
|------|------|
| `config/config.toml` | 配置文件 |
| `sentences.db` | SQLite 数据库 |

几点提醒：

- 目录权限不用管：容器启动时读 `./data` 的属主并以同一 uid/gid 运行；确实要
  强制运行用户时在 compose 里设 `PUID` / `PGID`。
- 镜像里的依赖按 `uv.lock` 安装，FastAPI 这些包的版本与仓库锁定的一致。
- 改端口要改两处：`data/config/config.toml` 的 `server.port`，以及
  `docker-compose.yml` 的端口映射。
- 镜像只支持 `linux/amd64`；NAS/树莓派等 ARM 设备请改用源码或 wheel 部署。
- 健康检查打 `/api/sentences?limit=1`。

> ⚠️ 这个服务没有登录和鉴权，增删改与导入接口对任何能访问到的人都开放。
> compose 默认只映射到 `127.0.0.1`；要给局域网用就改成 `8000:8000`，并且
> 按下面「安全提醒」那一节加一层带认证的反向代理。

## 🚀 部署为 systemd 服务（推荐）

### 创建服务文件

```bash
sudo nano /etc/systemd/system/sentence-api.service
```

填入以下内容（请根据实际路径和用户修改）：

```ini
[Unit]
Description=Sentence API Service
After=network.target

[Service]
Type=simple
User=你的用户名
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/你的用户名/.local/bin/sentence-api
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

如果使用虚拟环境：

```ini
ExecStart=/home/你的用户名/sentence_api/.venv/bin/sentence-api
```

### 启动并设置开机自启

```bash
sudo systemctl daemon-reload
sudo systemctl start sentence-api
sudo systemctl enable sentence-api
sudo systemctl status sentence-api
```

### 查看日志

```bash
sudo journalctl -u sentence-api -f
```

## 📚 API 接口

### 1. 随机获取句子

```text
GET /api/random
```

**参数**（可选）：

| 参数名   | 类型   | 说明                     |
| -------- | ------ | ------------------------ |
| category | string | 分类名，例如 `category=励志` |

**示例响应**：

```json
{
  "id": 42,
  "hitokoto": "生活不止眼前的苟且",
  "author": "高晓松",
  "categories": ["励志", "经典"],
  "commit_from": "web",
  "created_at": 1744567890,
  "length": 10
}
```

### 2. 获取句子列表（分页）

```text
GET /api/sentences?page=1&limit=20
```

### 3. 添加句子

```text
POST /api/sentences
```

**请求体**：

```json
{
  "hitokoto": "句子内容",
  "author": "作者",
  "categories": ["分类1", "分类2"],
  "commit_from": "web"
}
```

### 4. 更新句子

```text
PUT /api/sentences/{id}
```

### 5. 删除句子

```text
DELETE /api/sentences/{id}
```

### 6. 获取所有分类

```text
GET /api/categories
```

### 7. 新增分类

```text
POST /api/categories?name=分类名
```

### 8. 删除分类

```text
DELETE /api/categories/{name}
```

### 9. 批量导入（JSON 文件）

```text
POST /api/import
```

- 表单参数 `file`: JSON 数组文件
- 表单参数 `replace`: `true` 或 `false`（是否清空现有数据）

### 10. 导出所有句子

```text
GET /api/export
```

## 📂 数据格式

### 导入/导出的 JSON 数组示例

```json
[
  {
    "hitokoto": "你是我记忆里偶尔会去拜访的一座墓园",
    "author": "佚名",
    "categories": ["散文", "伤感"],
    "commit_from": "import_script",
    "created_at": 1744567890,
    "length": 20
  }
]
```

- `created_at` 和 `length` 可选，导入时会自动补全
- 若未提供 `categories`，将自动归为"默认分类"

## 🎨 前端管理界面功能

- ✅ 添加/编辑句子（支持多选分类）
- 🏷️ 管理分类（新增、删除）
- 📋 分页展示句子列表
- ✏️ 编辑、删除操作
- 📤 导入 JSON 文件（追加或替换模式）
- 📥 导出全部句子为 JSON

## 🛡️ 安全提醒

- 本服务默认**无任何鉴权**，适合个人内网使用或本地运行。
- 如需对外暴露，建议在前面加一层反向代理（如 Nginx）并配置 Basic Auth 或 API Key。

## 📄 许可证

MIT License

---

**Enjoy!** 🎉
