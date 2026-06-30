# AI Knowledge System — Start Guide（上手与迁移指南）

本手册面向两类场景：

- 新用户第一次使用本项目。
- 你在新电脑/新环境上迁移并恢复可用状态。

目标是用最少步骤跑起来，并能在需要时完整迁移数据。

## 1. 你会得到什么

启动后你将拥有以下能力：

- Open WebUI 对话入口（连接到本项目的 OpenAI 兼容接口）。
- `rag-api` 记忆增强对话（分层记忆 + 文档挂载）。
- `doc-reader` 文档上传、分段、问答。
- Qdrant 持久化向量存储（记忆和文档）。

## 2. 环境前置

### 必需条件

- Docker Desktop（Windows）或 Docker Engine + Compose（Linux/macOS）。
- DeepSeek API Key（用于默认对话模型）。

### 推荐检查

```powershell
# 确认 Docker 可用
docker --version
docker compose version
```

## 3. 10 分钟首次启动

在项目根目录执行。

### 步骤 1：准备 `.env`

```powershell
# Windows PowerShell
"DEEPSEEK_API_KEY=sk-your-key-here" | Out-File -Encoding utf8 .env
```

如果你已有 `.env`，跳过此步。

### 步骤 2：启动服务

```powershell
docker compose up -d
```

### 步骤 3：拉取 embedding 模型

```powershell
docker compose exec ollama ollama pull nomic-embed-text
```

### 步骤 4：健康检查

```powershell
curl --noproxy "*" http://localhost:18000/health
curl --noproxy "*" http://localhost:19000/health
curl --noproxy "*" http://localhost:18000/v1/models
```

预期返回 `{"status":"ok"}` 与模型列表。

## 4. 服务入口总览

| 服务 | 地址 | 用途 |
|------|------|------|
| Open WebUI | http://localhost:8088 | 对话前端 |
| rag-api | http://localhost:18000 | 聊天 API + 记忆系统 |
| doc-reader | http://localhost:19000 | 文档上传与文档问答 |
| Qdrant Dashboard | http://localhost:6333/dashboard | 向量库查看 |

说明：当前 `docker-compose.yml` 中 Open WebUI 端口映射是 `8088:8080`。

## 5. Open WebUI 接入（一次配置）

在 Open WebUI 管理界面添加 OpenAI 兼容连接：

- API URL: `http://host.docker.internal:18000/v1`
- API Key: 留空
- 模型 ID: 可先留空

如果你在 Linux Docker 环境中 `host.docker.internal` 不可用，可改为宿主机可达地址（例如局域网 IP）。

## 6. 核心使用方式

### 6.1 记忆层切换

- `general`: 通用层
- `story`: 创作层
- `docreader`: 文档分析层
- `core`: 核心层（始终生效，不直接切换）

调用方式：

- 模型 ID 直接写层名，例如 `story`
- 或使用 `模型:层级`，例如 `deepseek-v4-flash:story`

### 6.2 常用 API

```powershell
# 查看当前层
curl --noproxy "*" http://localhost:18000/role

# 切换层
curl --noproxy "*" -X POST http://localhost:18000/role ^
  -H "Content-Type: application/json" ^
  -d "{\"role\":\"story\"}"

# 查看最近一次完整 prompt（排障有用）
curl --noproxy "*" http://localhost:18000/v1/last-prompt
```

### 6.3 文档工作流

```powershell
# 上传文档
curl --noproxy "*" -X POST http://localhost:19000/documents/upload -F "file=@小说.txt"

# 列出文档
curl --noproxy "*" http://localhost:19000/documents

# 挂载文档到 rag-api
curl --noproxy "*" -X POST http://localhost:18000/documents/active ^
  -H "Content-Type: application/json" ^
  -d "{\"doc_ids\":[\"文档ID\"]}"
```

## 7. 新电脑迁移指南（无数据）

适用于“代码和配置迁移，但不迁移历史记忆数据”。

1. 安装 Docker。
2. 拉取项目代码到本地。
3. 创建 `.env` 并写入 `DEEPSEEK_API_KEY`。
4. 执行：

```powershell
docker compose up -d
docker compose exec ollama ollama pull nomic-embed-text
```

5. 按第 3 节健康检查确认服务可用。

## 8. 新电脑迁移指南（含数据）

适用于“要保留历史记忆与文档向量”。

### 8.1 在旧机器备份 Qdrant 卷

```powershell
# 在项目根目录执行，生成 qdrant-backup.tar.gz
docker run --rm -v ai-knowledge-system_qdrant-data:/data -v ${PWD}:/backup alpine tar czf /backup/qdrant-backup.tar.gz -C /data .
```

### 8.2 在新机器恢复 Qdrant 卷

先执行一次 `docker compose up -d` 以创建卷，再恢复：

```powershell
docker run --rm -v ai-knowledge-system_qdrant-data:/data -v ${PWD}:/backup alpine tar xzf /backup/qdrant-backup.tar.gz -C /data
```

然后重启 Qdrant 与业务服务：

```powershell
docker compose restart qdrant rag-api doc-reader
```

### 8.3 备份建议

- 每次大版本升级前做一次 Qdrant 备份。
- 建议同时备份 `.env`（不要提交到 Git）。

## 9. 日常运维命令

```powershell
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f rag-api
docker compose logs -f doc-reader

# 重启单个服务
docker compose restart rag-api

# 停止全部服务
docker compose down
```

## 10. 常见问题（快速定位）

### 10.1 聊天 500 报错

优先检查：

- `DEEPSEEK_API_KEY` 是否存在且有效。
- `ollama` 是否已拉取 `nomic-embed-text`。
- `rag-api` 日志中是否有连接 Qdrant 失败。

### 10.2 文档上传后检索不到内容

优先检查：

- 是否是文本型 PDF（扫描件通常无文字层）。
- 文档是否已被挂载到 `/documents/active`。

### 10.3 Open WebUI 无法连到 rag-api

优先检查：

- API URL 是否为 `http://host.docker.internal:18000/v1`。
- 端口是否与当前 compose 一致（Open WebUI 对外是 `8088`）。
