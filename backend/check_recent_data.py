#!/usr/bin/env python3
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select, func, text
from app.db.session import get_session
from app.models.print_job import PrintJob
from app.models.consumption_record import ConsumptionRecord

async def check_recent_data():
    async for session in get_session():
        # 检查最近48小时的打印任务
        job_count = await session.scalar(
            select(func.count(PrintJob.id)).where(PrintJob.updated_at > text('NOW() - INTERVAL \'48 hours\''))
        )
        print(f'最近48小时的打印任务数: {job_count}')
        
        # 检查最近48小时的消耗记录
        record_count = await session.scalar(
            select(func.count(ConsumptionRecord.id)).where(ConsumptionRecord.created_at > text('NOW() - INTERVAL \'48 hours\''))
        )
        print(f'最近48小时的消耗记录数: {record_count}')
        
        # 获取最近的几个打印任务
        recent_jobs = (await session.execute(
            select(PrintJob).order_by(PrintJob.updated_at.desc()).limit(5)
        )).scalars().all()
        
        for job in recent_jobs:
            print(f'打印任务: ID={job.id}, 文件={job.file_name}, 状态={job.status}, 创建={job.created_at}')
            # 检查每个任务的消耗记录数
            record_count_for_job = await session.scalar(
                select(func.count(ConsumptionRecord.id)).where(ConsumptionRecord.job_id == job.id)
            )
            print(f'  -> 关联的消耗记录数: {record_count_for_job}')
            
            # 检查每个任务是否有多个消耗记录
            records = (await session.execute(
                select(ConsumptionRecord).where(ConsumptionRecord.job_id == job.id)
            )).scalars().all()
            
            if len(records) > 1:
                print(f'  -> 警告: 任务有多个消耗记录!')
                for idx, record in enumerate(records):
                    print(f'    记录 {idx+1}: tray_id={record.tray_id}, grams={record.grams}, source={record.source}')

if __name__ == "__main__":
    asyncio.run(check_recent_data())