# 3D Consumables Management（拓竹耗材管理系统）

本项目是一个可在局域网使用的拓竹耗材管理系统：通过 **LAN MQTT** 读取打印机状态与 AMS 托盘信息，结合耗材卷管理与托盘绑定，生成可审计的消耗账本与成本统计，并提供 Web UI 实时展示。

## 目录结构

- `backend/`：FastAPI + SQLAlchemy + Alembic（业务与 API）
- `collector/`：MQTT 采集器（订阅 `device/<serial>/report` 并落库）
- `frontend/`：Next.js Web UI
- `docs/`：实现说明与局域网读取参考

## 快速启动（Docker Compose）

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

## 开发模式（不使用 Docker）

- 后端：见 `backend/README.md`
- 前端：见 `frontend/README.md`
- 采集器：见 `collector/README.md`


