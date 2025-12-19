# 3D Consumables Management（拓竹耗材管理系统）

本项目是一个可在局域网使用的拓竹耗材管理系统：通过 **LAN MQTT** 读取打印机状态与 AMS 托盘信息，结合耗材卷管理与托盘绑定，生成可审计的消耗账本与成本统计，并提供 Web UI 实时展示。

## 目录结构

- `backend/`：FastAPI + SQLAlchemy + Alembic（业务与 API）
- `collector/`：MQTT 采集器（订阅 `device/<serial>/report` 并落库）
- `frontend/`：Next.js Web UI
- `docs/`：实现说明与局域网读取参考
- `.github/workflows/`：GitHub Actions 工作流配置

## 快速启动（Docker Compose）

### 使用本地构建镜像

1) 复制环境变量模板并按需修改：

```bash
cp env.example .env
```

2) 启动：

```bash
docker compose up --build
```

3) 访问：

- 后端 API：`http://localhost:8000/docs`
- 前端 UI：`http://localhost:3000`

### 使用GitHub Container Registry镜像

1) 复制GitHub Container Registry环境变量模板：

```bash
cp env.ghcr.example .env
```

2) 修改.env文件中的IMAGE_OWNER为你的GitHub用户名或组织名

3) 启动：

```bash
docker compose -f docker-compose.ghcr.yml up
```

## GitHub Actions CI/CD

本项目使用GitHub Actions自动化Docker镜像的构建和推送：

### 触发条件
- 推送到main分支：构建并推送带有`latest`标签的镜像
- 创建Git标签（vX.Y.Z格式）：构建并推送带有对应版本标签的镜像

### 构建流程
1. 运行各服务的测试
2. 并行构建三个服务的Docker镜像（api、collector、frontend）
3. 推送镜像到GitHub Container Registry

### 镜像命名
- API服务：`ghcr.io/你的用户名/3d-consumables-api:标签`
- 采集器服务：`ghcr.io/你的用户名/3d-consumables-collector:标签`
- 前端服务：`ghcr.io/你的用户名/3d-consumables-frontend:标签`

### 使用预构建镜像
如果你想使用预构建的镜像而不是本地构建，可以使用`docker-compose.ghcr.yml`文件。请确保先配置好`env.ghcr.example`中的环境变量。

## 开发模式（不使用 Docker）

- 后端：见 `backend/README.md`
- 前端：见 `frontend/README.md`
- 采集器：见 `collector/README.md`


