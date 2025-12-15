# backend（FastAPI）

## 本地运行（不使用 Docker）

1) 创建虚拟环境并安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) 设置环境变量（示例）：

```bash
export DATABASE_URL="postgresql+asyncpg://consumables:consumables@localhost:5432/consumables"
export APP_SECRET_KEY="dev-secret-change-me"
export ALLOW_INSECURE_MQTT_TLS="true"
```

3) 运行迁移并启动：

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

访问：`http://localhost:8000/docs`


