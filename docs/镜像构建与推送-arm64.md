## 目标

将本项目的 3 个服务镜像（`api` / `collector` / `frontend`）以 **linux/arm64** 架构构建并推送到私有仓库 `192.168.5.54:5000`，镜像名统一带 `-arm`，tag 使用 **语义化版本 + latest**。

## 镜像命名规范（固定）

- `192.168.5.54:5000/bambu-consumables/api-arm:{tag}`
- `192.168.5.54:5000/bambu-consumables/collector-arm:{tag}`
- `192.168.5.54:5000/bambu-consumables/frontend-arm:{tag}`

其中 `{tag}` 形如：

- `vX.Y.Z`（例如 `v1.0.0`）
- `latest`

## 前置条件

- Docker 已安装并开启 BuildKit / buildx
- 账号已具备向 `192.168.5.54:5000` 推送镜像的权限

登录私有仓库：

```bash
docker login 192.168.5.54:5000
```

## 初始化 buildx（一次性）

如果你还没有 buildx builder：

```bash
docker buildx create --name bambu --use
docker buildx inspect --bootstrap
```

如已存在，可直接：

```bash
docker buildx use bambu
docker buildx inspect --bootstrap
```

## 构建并推送（推荐命令）

在项目根目录执行（将 `TAG` 替换成你要发布的版本）：

```bash
REGISTRY_PREFIX="192.168.5.54:5000/bambu-consumables"
TAG="v1.0.0"

docker buildx build --platform linux/arm64 \
  -t "${REGISTRY_PREFIX}/api-arm:${TAG}" \
  -t "${REGISTRY_PREFIX}/api-arm:latest" \
  --push ./backend

docker buildx build --platform linux/arm64 \
  -t "${REGISTRY_PREFIX}/collector-arm:${TAG}" \
  -t "${REGISTRY_PREFIX}/collector-arm:latest" \
  --push ./collector

docker buildx build --platform linux/arm64 \
  -t "${REGISTRY_PREFIX}/frontend-arm:${TAG}" \
  -t "${REGISTRY_PREFIX}/frontend-arm:latest" \
  --push ./frontend
```

## 校验推送结果

在任意目标机器上拉取验证：

```bash
REGISTRY_PREFIX="192.168.5.54:5000/bambu-consumables"
TAG="v1.0.0"

docker pull "${REGISTRY_PREFIX}/api-arm:${TAG}"
docker pull "${REGISTRY_PREFIX}/collector-arm:${TAG}"
docker pull "${REGISTRY_PREFIX}/frontend-arm:${TAG}"
```

## 回滚建议

- **上线时尽量固定到版本 tag**（如 `v1.0.0`），避免 `latest` 漂移导致不确定性。
- 回滚时将 `docker-compose.prod.yml` 中 `IMAGE_TAG` 改回上一个稳定版本（如 `v0.9.5`），然后执行 `docker compose pull && docker compose up -d`。

