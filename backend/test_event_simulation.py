#!/usr/bin/env python3
"""
测试脚本：模拟打印任务结束事件，验证日志输出
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

async def simulate_print_ended_event():
    """模拟打印任务结束事件"""
    from app.db.models.normalized_event import NormalizedEvent
    from app.db.models.print_job import PrintJob
    from app.services.event_processor import process_event
    from app.db.session import async_session_factory
    from sqlalchemy import select, text
    
    # 创建模拟事件
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
    
    async with async_session_factory() as session:
        # 检查是否已有测试任务
        existing_job = await session.execute(
            text("SELECT id FROM print_jobs WHERE printer_id = 'test-printer' AND job_key = 'test-job:1' LIMIT 1")
        )
        job = existing_job.scalar_one_or_none()
        
        if not job:
            # 创建测试打印任务
            job = PrintJob(
                printer_id="test-printer",
                job_key="test-job:1",
                status="running",
                started_at=datetime.now(timezone.utc),
                data_json=event_data,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            print(f"创建测试打印任务: {job.id}")
        else:
            print(f"使用现有测试打印任务: {job}")
        
        # 创建打印结束事件
        event = NormalizedEvent(
            printer_id="test-printer",
            type="PrintEnded",
            occurred_at=datetime.now(timezone.utc),
            data_json=event_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        print(f"创建打印结束事件: {event.id}")
        
        # 处理事件
        print("开始处理打印结束事件...")
        await process_event(session, event)
        
        # 再次创建相同的打印结束事件，测试幂等性
        print("\n创建重复的打印结束事件，测试幂等性...")
        event2 = NormalizedEvent(
            printer_id="test-printer",
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
