#!/usr/bin/env python3
"""
Docker 内部测试脚本：模拟完整打印流程，验证耗材消耗日志
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

async def simulate_full_print_process():
    """模拟完整打印流程"""
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
        job_key = f"{printer_id}:full-test-{str(uuid4())[:8]}"
        
        # 基础事件数据
        base_event_data = {
            "print": {
                "tray_now": [
                    {
                        "id": "1",
                        "remain": 1000,
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
            "gcode_file": "full_test_model.gcode",
            "tray_now": [
                {
                    "id": "1",
                    "remain": 1000,
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
        
        # 1. 创建打印开始事件
        start_event_data = dict(base_event_data)
        start_event_data["print"]["gcode_state"] = "PREPARE"
        
        start_event = NormalizedEvent(
            event_id=f"start-event-{str(uuid4())[:8]}",
            printer_id=printer_id,
            type="PrintStarted",
            occurred_at=datetime.now(timezone.utc),
            data_json=start_event_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(start_event)
        await session.commit()
        await session.refresh(start_event)
        print(f"\n创建打印开始事件: {start_event.id}, printer_id={printer_id}")
        
        # 处理开始事件
        print("处理打印开始事件...")
        await process_event(session, start_event)
        
        # 2. 创建打印进度事件
        progress_event_data = dict(base_event_data)
        progress_event_data["print"]["gcode_state"] = "PRINTING"
        progress_event_data["print"]["mc_percent"] = 50
        progress_event_data["print"]["tray_now"][0]["remain"] = 950
        
        progress_event = NormalizedEvent(
            event_id=f"progress-event-{str(uuid4())[:8]}",
            printer_id=printer_id,
            type="PrintProgress",
            occurred_at=datetime.now(timezone.utc),
            data_json=progress_event_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(progress_event)
        await session.commit()
        await session.refresh(progress_event)
        print(f"\n创建打印进度事件: {progress_event.id}, printer_id={printer_id}")
        
        # 处理进度事件
        print("处理打印进度事件...")
        await process_event(session, progress_event)
        
        # 3. 创建多个结束事件，模拟可能的重复事件
        end_event_data = dict(base_event_data)
        end_event_data["print"]["gcode_state"] = "FINISH"
        end_event_data["print"]["tray_now"][0]["remain"] = 900
        
        end_event1 = NormalizedEvent(
            event_id=f"end-event-1-{str(uuid4())[:8]}",
            printer_id=printer_id,
            type="PrintEnded",
            occurred_at=datetime.now(timezone.utc),
            data_json=end_event_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(end_event1)
        await session.commit()
        await session.refresh(end_event1)
        print(f"\n创建第一个打印结束事件: {end_event1.id}, printer_id={printer_id}")
        
        # 处理第一个结束事件
        print("处理第一个打印结束事件...")
        await process_event(session, end_event1)
        
        # 稍等一下，模拟一些时间间隔
        await asyncio.sleep(1)
        
        # 创建第二个结束事件，模拟可能的重复事件
        end_event2 = NormalizedEvent(
            event_id=f"end-event-2-{str(uuid4())[:8]}",
            printer_id=printer_id,
            type="PrintEnded",
            occurred_at=datetime.now(timezone.utc),
            data_json=end_event_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(end_event2)
        await session.commit()
        await session.refresh(end_event2)
        print(f"\n创建第二个打印结束事件: {end_event2.id}, printer_id={printer_id}")
        
        # 处理第二个结束事件
        print("处理第二个打印结束事件...")
        await process_event(session, end_event2)
        
        # 再稍等一下，模拟一些时间间隔
        await asyncio.sleep(1)
        
        # 创建第三个结束事件，再次模拟可能的重复事件
        end_event3 = NormalizedEvent(
            event_id=f"end-event-3-{str(uuid4())[:8]}",
            printer_id=printer_id,
            type="PrintEnded",
            occurred_at=datetime.now(timezone.utc),
            data_json=end_event_data,
            created_at=datetime.now(timezone.utc),
        )
        session.add(end_event3)
        await session.commit()
        await session.refresh(end_event3)
        print(f"\n创建第三个打印结束事件: {end_event3.id}, printer_id={printer_id}")
        
        # 处理第三个结束事件
        print("处理第三个打印结束事件...")
        await process_event(session, end_event3)
        
        print("\n完整打印流程测试完成，请检查日志输出以分析耗材消耗情况")

if __name__ == "__main__":
    asyncio.run(simulate_full_print_process())
