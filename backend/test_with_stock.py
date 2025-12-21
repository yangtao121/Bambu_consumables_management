#!/usr/bin/env python3
"""
Docker 内部测试脚本：使用现有库存，然后模拟打印任务，验证耗材消耗
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

async def simulate_print_with_stock():
    """使用现有库存，然后模拟打印任务"""
    from app.services.event_processor import process_event
    from app.db.session import async_session_factory
    from app.db.models.normalized_event import NormalizedEvent
    from app.db.models.print_job import PrintJob
    from app.db.models.printer import Printer
    from app.db.models.material_stock import MaterialStock
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
        job_key = f"{printer_id}:stock-test-{str(uuid4())[:8]}"
        
        # 获取现有库存
        result = await session.execute(text("SELECT id, material, color, brand, remaining_grams FROM material_stocks WHERE material='PLA' AND color='白色' AND brand='BBL' AND is_archived=false LIMIT 1"))
        stock = result.fetchone()
        
        if stock:
            stock_id = str(stock[0])  # 转换为字符串
            print(f"使用现有库存: {stock_id}, 材料={stock[1]}, 颜色={stock[2]}, 品牌={stock[3]}, 剩余量={stock[4]}g")
            
            # 创建打印任务的快照，包含库存信息
            event_data = {
                "print": {
                    "gcode_state": "FINISH",
                    "tray_now": [
                        {
                            "id": "1",
                            "remain": 900,
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
                "gcode_file": "stock_test_model.gcode",
                "tray_now": [
                    {
                        "id": "1",
                        "remain": 900,
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
            
            # 创建打印任务的快照，包含托盘到库存的映射
            spool_binding_snapshot = {
                "tray_to_stock": {
                    "1": stock_id  # 托盘ID 1 映射到我们的库存ID
                },
                "start_remain_by_tray": {
                    "1": 1000  # 打印开始时的余量
                },
                "trays_seen": [1],
                "tray_meta_by_tray": {
                    "1": {
                        "material": "PLA",
                        "color": "FFFFFF",
                        "brand": "BBL"
                    }
                }
            }
            
            # 创建测试打印任务
            job = PrintJob(
                printer_id=printer_id,
                job_key=job_key,
                status="running",
                started_at=datetime.now(timezone.utc),
                spool_binding_snapshot_json=spool_binding_snapshot,
                file_name="stock_test_model.gcode",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            print(f"创建测试打印任务: {job.id}, printer_id={printer_id}, job_key={job_key}")
            
            # 创建打印结束事件
            event_id = f"stock-event-{str(uuid4())[:8]}"
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
            print("\n开始处理打印结束事件...")
            await process_event(session, event)
            
            # 再次创建相同的打印结束事件，测试幂等性
            print("\n创建重复的打印结束事件，测试幂等性...")
            event2_id = f"stock-event-{str(uuid4())[:8]}"
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
            
            # 检查库存变更
            result = await session.execute(
                text(f"SELECT id, remaining_grams FROM material_stocks WHERE id = '{stock_id}'")
            )
            stock_after = result.fetchone()
            if stock_after:
                print(f"\n处理后库存: stock_id={stock_after[0]}, 剩余量={stock_after[1]}g")
            
            # 检查消耗记录
            result = await session.execute(
                text(f"SELECT job_id, tray_id, grams, grams_effective, source FROM consumption_records WHERE job_id = '{job.id}'")
            )
            consumption_records = result.fetchall()
            if consumption_records:
                print("\n消耗记录:")
                for record in consumption_records:
                    print(f"  job_id={record[0]}, tray_id={record[1]}, grams={record[2]}, grams_effective={record[3]}, source={record[4]}")
            else:
                print("\n没有找到消耗记录")
                
            # 检查库存变更记录
            result = await session.execute(
                text(f"SELECT stock_id, delta_grams, reason, kind, job_id FROM material_ledger WHERE stock_id = '{stock_id}' ORDER BY created_at DESC LIMIT 5")
            )
            ledger_records = result.fetchall()
            if ledger_records:
                print("\n库存变更记录:")
                for record in ledger_records:
                    print(f"  stock_id={record[0]}, delta_grams={record[1]}, reason={record[2]}, kind={record[3]}, job_id={record[4]}")
            else:
                print("\n没有找到库存变更记录")
        else:
            print("没有找到合适的库存，测试终止")

if __name__ == "__main__":
    asyncio.run(simulate_print_with_stock())