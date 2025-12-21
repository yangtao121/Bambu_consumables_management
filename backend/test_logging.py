#!/usr/bin/env python3
"""
测试脚本：验证日志输出是否正常工作
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/consumption_test.log')
    ]
)

async def test_logging():
    """测试日志输出"""
    logger = logging.getLogger("test_logging")
    
    logger.info("开始测试日志输出...")
    
    # 测试事件处理日志
    logger.info("开始处理事件: printer_id=test-printer, job_key=test-job:1, event_type=PrintEnded, occurred_at=2023-01-01T12:00:00Z")
    
    # 测试状态变更日志
    logger.info("打印任务状态变更: job_id=test-job-id, event_type=PrintEnded, gcode_state=FINISH, old_status=running, new_status=ended")
    
    # 测试结算触发日志
    logger.info("准备结算耗材消耗: job_id=test-job-id, status=ended, ended_at=2023-01-01T12:30:00Z")
    logger.info("使用AMS校准结算模式: job_id=test-job-id")
    
    # 测试库存变更日志
    logger.info(
        "库存变更开始: stock_id=test-stock-id, material=PLA, color=白色, "
        "before=1000g, delta=-50g, effective_delta=-50g, after=950g, "
        "kind=consumption, reason=consumption job=test-job-id tray=1 seg=0 source=ams_remain_start_end_grams, job_id=test-job-id"
    )
    logger.info("库存变更完成: stock_id=test-stock-id, ledger_id=test-ledger-id, new_remaining=950g")
    
    # 测试消耗记录创建日志
    logger.info(
        "创建消耗记录(AMS校准-剩余量差值): id=test-consumption-id, job_id=test-job-id, stock_id=test-stock-id, "
        "tray_id=1, grams=50, source=ams_remain_start_end_grams, confidence=medium"
    )
    
    logger.info("日志测试完成")

if __name__ == "__main__":
    asyncio.run(test_logging())
