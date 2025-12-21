#!/usr/bin/env python3
import os
import sys

# 模拟Docker环境的导入方式
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 设置环境变量
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://postgres:password@db/consumables')

from sqlalchemy import select, func, text
from app.db.session import get_session
from app.models.print_job import PrintJob
from app.models.consumption_record import ConsumptionRecord

if __name__ == "__main__":
    print("Test script for checking imports")
