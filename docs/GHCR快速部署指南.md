# GHCR快速部署指南

本指南用于使用GitHub Container Registry (GHCR)的预构建镜像快速部署3D耗材管理系统。

## 镜像信息

所有镜像来源于 `ghcr.io/yangtao121`：
- API服务：`ghcr.io/yangtao121/3d-consumables-api`
- 采集器服务：`ghcr.io/yangtao121/3d-consumables-collector`
- 前端服务：`ghcr.io/yangtao121/3d-consumables-frontend`

## 一键部署

### 方式一：使用curl直接部署

对于大多数用户，可以使用以下命令直接部署（默认配置）：

```bash
# 创建并启动服务（使用默认配置）
curl -fsSL https://raw.githubusercontent.com/yangtao121/3d-consumables-management/main/docker-compose.ghcr.yml | docker compose -f - up -d

# 查看服务状态
docker compose -f https://raw.githubusercontent.com/yangtao121/3d-consumables-management/main/docker-compose.ghcr.yml ps
```

### 方式二：自定义配置后部署

如果需要自定义配置：

```bash
# 1. 下载配置文件
wget https://raw.githubusercontent.com/yangtao121/3d-consumables-management/main/docker-compose.ghcr.yml
wget https://raw.githubusercontent.com/yangtao121/3d-consumables-management/main/env.ghcr.example -O .env

# 2. 编辑配置（可选）
nano .env

# 3. 启动服务
docker compose -f docker-compose.ghcr.yml up -d
```

## 配置说明

### 默认配置

以下为默认配置，无需修改即可使用：
- 数据库：PostgreSQL 16
- API端口：8000
- 前端端口：3000
- 镜像标签：latest

### 自定义配置

您可以通过修改 `.env` 文件来自定义以下关键配置：

```bash
# 数据库配置
POSTGRES_DB=consumables
POSTGRES_USER=consumables
POSTGRES_PASSWORD=consumables

# 应用配置
APP_SECRET_KEY=your-secure-secret-key
APP_ENV=prod

# 端口配置
API_PORT=8000
FRONTEND_PORT=3000

# 前端API访问地址（重要：部署时需替换为实际服务器IP）
NEXT_PUBLIC_API_BASE_URL=http://your-server-ip:8000

# 可选：指定镜像版本
IMAGE_TAG=latest  # 或指定具体版本如 v1.0.0
```

## 数据持久化

本系统使用Docker卷实现数据持久化：
- `db_data`：存储PostgreSQL数据库数据
- `logs_data`：存储应用程序日志

查看数据卷：
```bash
docker volume ls | grep -E 'db_data|logs_data'
```

## 验证部署

访问以下地址验证部署是否成功：
- 前端界面：`http://your-server-ip:3000`
- API文档：`http://your-server-ip:8000/docs`
- 健康检查：`http://your-server-ip:8000/health`

## 常用运维命令

```bash
# 查看服务状态
docker compose -f docker-compose.ghcr.yml ps

# 查看日志
docker compose -f docker-compose.ghcr.yml logs -f api
docker compose -f docker-compose.ghcr.yml logs -f collector

# 重启服务
docker compose -f docker-compose.ghcr.yml restart

# 停止服务（保留数据）
docker compose -f docker-compose.ghcr.yml down

# 更新到最新版本
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```

## 常见问题

### 1. 前端无法连接后端API

**问题**：前端显示"无法连接服务器"

**解决方案**：检查 `.env` 文件中的 `NEXT_PUBLIC_API_BASE_URL` 是否设置为正确的服务器IP地址：

```bash
# 错误示例（本地localhost）
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# 正确示例（替换为实际服务器IP）
NEXT_PUBLIC_API_BASE_URL=http://192.168.1.100:8000
```

### 2. 容器启动失败

**问题**：容器启动后立即退出

**解决方案**：查看日志排查问题：

```bash
docker compose -f docker-compose.ghcr.yml logs api
docker compose -f docker-compose.ghcr.yml logs collector
docker compose -f docker-compose.ghcr.yml logs frontend
```

### 3. 数据库连接失败

**问题**：API或采集器无法连接数据库

**解决方案**：确保数据库容器正常启动：

```bash
# 检查数据库容器状态
docker compose -f docker-compose.ghcr.yml ps db

# 重启数据库容器
docker compose -f docker-compose.ghcr.yml restart db
```

### 4. 如何使用特定版本

**解决方案**：在 `.env` 文件中指定 `IMAGE_TAG`：

```bash
# 使用v1.0.0版本
IMAGE_TAG=v1.0.0

# 然后重新部署
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```

## 备份与恢复

请参考 [备份与恢复指南](备份与恢复.md) 了解如何备份和恢复数据。
