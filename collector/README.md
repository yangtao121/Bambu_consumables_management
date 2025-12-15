# collector（MQTT 采集器）

采集器会从数据库 `printers` 表读取已配置的打印机，逐台连接其 LAN MQTT（TLS 8883），订阅 `device/<serial>/report`，并将：\n\n- 原始消息写入 `raw_events`\n- 标准化事件写入 `normalized_events`\n\n## 本地运行（不使用 Docker）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+asyncpg://consumables:consumables@localhost:5432/consumables"
export APP_SECRET_KEY="dev-secret-change-me"
python -m collector.main
```


