#!/usr/bin/env python3
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
import os

# 创建PDF文件
doc = SimpleDocTemplate("3D耗材管理系统宣传单.pdf", pagesize=A4)
story = []

# 获取样式
styles = getSampleStyleSheet()

# 自定义标题样式
title_style = ParagraphStyle(
    'CustomTitle',
    parent=styles['Heading1'],
    fontSize=24,
    spaceAfter=20,
    textColor=HexColor('#1a365d'),
    alignment=1  # 居中
)

# 自定义标题2样式
heading2_style = ParagraphStyle(
    'CustomHeading2',
    parent=styles['Heading2'],
    fontSize=16,
    spaceAfter=10,
    textColor=HexColor('#2a4365')
)

# 自定义正文样式
body_style = ParagraphStyle(
    'CustomBody',
    parent=styles['Normal'],
    fontSize=12,
    spaceAfter=10,
    alignment=4  # 两端对齐
)

# 添加标题
story.append(Paragraph("3D耗材管理系统", title_style))
story.append(Spacer(1, 12))

# 添加系统简介
story.append(Paragraph("专为拓竹打印机设计的局域网耗材管理系统", heading2_style))
story.append(Paragraph(
    "通过LAN MQTT连接打印机，实时监控打印状态与AMS托盘信息，自动记录耗材消耗并生成成本统计。",
    body_style
))
story.append(Spacer(1, 12))

# 添加核心功能
story.append(Paragraph("核心功能", heading2_style))
features = [
    "<b>实时监控</b> - 获取打印机状态、打印进度和托盘信息",
    "<b>耗材管理</b> - 记录耗材信息，管理库存状态和托盘绑定",
    "<b>消耗追踪</b> - 自动记录打印消耗，支持多种计算策略",
    "<b>成本核算</b> - 根据耗材价格自动计算打印成本",
    "<b>数据报表</b> - 多维度统计分析，支持数据导出"
]

for feature in features:
    story.append(Paragraph(f"• {feature}", body_style))

story.append(Spacer(1, 12))

# 添加技术特点
story.append(Paragraph("技术特点", heading2_style))
tech_features = [
    "基于Next.js和FastAPI的现代Web应用",
    "Docker容器化部署，一键启动",
    "通过MQTT协议实时获取打印机数据",
    "PostgreSQL数据库存储，完整历史记录",
    "响应式设计，适配各种设备"
]

for feature in tech_features:
    story.append(Paragraph(f"• {feature}", body_style))

story.append(Spacer(1, 12))

# 添加部署指南
story.append(Paragraph("快速部署", heading2_style))
story.append(Paragraph(
    "系统要求：Docker 20.10+, Docker Compose v2.0+, 2GB内存, 5GB磁盘空间",
    body_style
))
story.append(Paragraph(
    "部署步骤：获取配置文件 → 设置环境变量 → 启动Docker Compose服务 → 访问Web界面",
    body_style
))

# 添加拼贴图
if os.path.exists("screenshots/collage.png"):
    collage = Image("screenshots/collage.png", width=16*cm, height=10*cm)
    collage.hAlign = 'CENTER'
    story.append(Spacer(1, 12))
    story.append(collage)
    story.append(Spacer(1, 12))

# 添加联系信息
story.append(Paragraph("项目地址", heading2_style))
story.append(
    Paragraph("https://github.com/yangtao121/3d-consumables-management", body_style)
)
story.append(Spacer(1, 6))
story.append(
    Paragraph("开源项目，遵循MIT许可证，欢迎自由使用、修改和分发。", body_style)
)

# 生成PDF
doc.build(story)
print("宣传单PDF已生成: 3D耗材管理系统宣传单.pdf")