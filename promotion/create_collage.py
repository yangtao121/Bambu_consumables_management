#!/usr/bin/env python3
from PIL import Image
import os

# 设置输出图片大小和布局
output_width = 1200
output_height = 800
cols = 3
rows = 2

# 计算每个小图片的大小
padding = 10
cell_width = (output_width - padding * (cols + 1)) // cols
cell_height = (output_height - padding * (rows + 1)) // rows

# 创建白色背景图片
collage = Image.new('RGB', (output_width, output_height), color='white')

# 要包含的截图及其描述
screenshots = [
    {"file": "dashboard.png", "title": "主页/仪表板"},
    {"file": "printers.png", "title": "打印机管理"},
    {"file": "stocks.png", "title": "耗材库存"},
    {"file": "jobs.png", "title": "打印历史"},
    {"file": "reports.png", "title": "数据报表"},
    {"file": "settings.png", "title": "系统设置"}
]

# 加载字体（如果可用）
try:
    from PIL import ImageFont
    title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    label_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
except:
    # 如果无法加载字体，使用默认字体
    title_font = None
    label_font = None

# 添加标题
title = "3D耗材管理系统 - 功能展示"
if title_font:
    from PIL import ImageDraw
    draw = ImageDraw.Draw(collage)
    text_width = draw.textlength(title, font=title_font)
    x = (output_width - text_width) // 2
    draw.text((x, 10), title, fill="black", font=title_font)
else:
    print("无法加载字体，跳过标题绘制")

# 处理每个截图
for i, screenshot in enumerate(screenshots):
    # 计算位置
    row = i // cols
    col = i % cols
    
    x = padding + col * (cell_width + padding)
    y = 40 + padding + row * (cell_height + padding)  # 40 是标题的高度
    
    # 打开截图并调整大小
    img_path = os.path.join("screenshots", screenshot["file"])
    if os.path.exists(img_path):
        img = Image.open(img_path)
        
        # 计算缩放比例，保持宽高比
        img_width, img_height = img.size
        scale = min(cell_width / img_width, cell_height / img_height)
        
        # 调整大小
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        img = img.resize((new_width, new_height))
        
        # 计算居中位置
        img_x = x + (cell_width - new_width) // 2
        img_y = y + (cell_height - new_height) // 2
        
        # 粘贴到拼贴图
        collage.paste(img, (img_x, img_y))
        
        # 添加标签
        if label_font:
            draw = ImageDraw.Draw(collage)
            text_width = draw.textlength(screenshot["title"], font=label_font)
            text_x = x + (cell_width - text_width) // 2
            draw.text((text_x, y + cell_height - 25), screenshot["title"], fill="black", font=label_font)
    else:
        print(f"截图文件不存在: {img_path}")

# 保存拼贴图
collage.save("screenshots/collage.png")
print("拼贴图已保存到: screenshots/collage.png")