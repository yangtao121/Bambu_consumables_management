#!/usr/bin/env python3
"""
Docker 内部测试脚本：模拟打印任务结束事件，验证日志输出
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

async def simulate_print_ended_event():
    """模拟打印任务结束事件"""
    from app.services.event_processor import process_event
    from app.db.session import async_session_factory
    from app.db.models.normalized_event import NormalizedEvent
    from app.db.models.print_job import PrintJob
    from app.db.models.printer import Printer
    from app.core.crypto import encrypt_str
    from app.core.config import settings
    from sqlalchemy import select, text
    
    async with async_session_factory() as session:
        # 获取现有打印机ID
        result = await session.execute(text("SELECT id FROM printers LIMIT 1"))
        printer_id = result.scalar()
        
        if not printer_id:
            # 如果没有现有打印机，创建一个
            printer = Printer(
                ip="192.168.1.100",
                serial="TEST-SN-" + str(uuid4())[:8],
                alias="Test Printer",
                model="A1 Mini",
                lan_access_code_enc=encrypt_str(settings.app_secret_key, "test-access-code"),
                status="idle",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(printer)
            await session.commit()
            await session.refresh(printer)
            printer_id = printer.id
            print(f"创建测试打印机: {printer_id}")
        else:
            print(f"使用现有打印机: {printer_id}")
        
        # 生成唯一的job_key
        job_key = f"{printer_id}:test-{str(uuid4())[:8]}"
        
        # 创建测试打印任务
        event_data = {
            "print": {
                "gcode_state": "FINISH",
                "tray_now": [
                    {
                        "id": "1",
                        "remain": 950,
                        "col": "FFFFFF",
                        "temp": 210,
                        "target_temp": 210,
                        "rpm": 0,
                        "flow": 0,
                        "diameter": 0,
                        "density": 0,
                        "tray_type_nm": "PLA",
                        "tray_info_brands": "BBL",
                        "tray_info_sn": "SN123456",
                        "tray_weight": 1000
                    }
                ]
            },
            "gcode_file": "test_model.gcode",
            "tray_now": [
                {
                    "id": "1",
                    "remain": 950,
                    "col": "FFFFFF",
                    "temp": 210,
                    "target_temp": 210,
                    "rpm": 0,
                    "flow": 0,
                    "diameter": 0,
                    "density": 0,
                    "tray_type_nm": "PLA",
                    "tray_info_brands": "BBL",
                    "tray_info_sn": "SN123456",
                    "tray_weight": 1000
                }
            ]
        }
        
        job = PrintJob(
            printer_id=printer_id,
            job_key=job_key,
            status="running",
            started_at=datetime.now(timezone.utc),
            spool_binding_snapshot_json=event_data,
            file_name="test_model.gcode",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        print(f"创建测试打印任务: {job.id}, printer_id={printer_id}, job_key={job_key}")
        
        # 创建打印结束事件
        event_id = f"test-event-{str(uuid4())[:8]}"
        event = NormalizedEvent(
            event_id=event_id,
            printer_id=printer_id,
            type="PrintEnded",
            occurred_at=datetime.now(timezone.utc),
            data_json=event_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        print(f"创建打印结束事件: {event.id}, printer_id={printer_id}, event_id={event_id}")
        
        # 处理事件
        print("开始处理打印结束事件...")
        await process_event(session, event)
        
        # 再次创建相同的打印结束事件，测试幂等性
        print("\n创建重复的打印结束事件，测试幂等性...")
        event2_id = f"test-event-{str(uuid4())[:8]}"
        event2 = NormalizedEvent(
            event_id=event2_id,
            printer_id=printer_id,
            type="PrintEnded",
            occurred_at=datetime.now(timezone.utc),
            data_json=event_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(event2)
        await session.commit()
        await session.refresh(event2)
        
        # 处理重复事件
        await process_event(session, event2)
        
        print("\n事件处理完成，请检查日志输出")

if __name__ == "__main__":
    asyncio.run(simulate_print_ended_event())