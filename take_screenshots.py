#!/usr/bin/env python3
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import chromedriver_autoinstaller

# 自动安装和设置ChromeDriver
chromedriver_autoinstaller.install()

# 设置Chrome选项
chrome_options = Options()
chrome_options.add_argument("--headless")  # 无头模式
chrome_options.add_argument("--window-size=1920,1080")  # 设置窗口大小
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# 初始化WebDriver
driver = webdriver.Chrome(options=chrome_options)
driver.set_page_load_timeout(30)

# 确保截图目录存在
os.makedirs("promotion/screenshots", exist_ok=True)

# 要截图的页面列表
pages = [
    {
        "name": "dashboard",
        "url": "http://localhost:3000/",
        "wait_element": "h1",  # 等待页面标题元素
        "description": "主页/仪表板"
    },
    {
        "name": "printers",
        "url": "http://localhost:3000/printers",
        "wait_element": "h1",
        "description": "打印机管理页面"
    },
    {
        "name": "stocks",
        "url": "http://localhost:3000/stocks",
        "wait_element": "h1",
        "description": "耗材库存页面"
    },
    {
        "name": "jobs",
        "url": "http://localhost:3000/jobs",
        "wait_element": "h1",
        "description": "打印任务历史页面"
    },
    {
        "name": "reports",
        "url": "http://localhost:3000/reports",
        "wait_element": "h1",
        "description": "数据报表页面"
    },
    {
        "name": "settings",
        "url": "http://localhost:3000/settings",
        "wait_element": "h1",
        "description": "系统设置页面"
    }
]

# 为每个页面截图
for page in pages:
    try:
        print(f"正在截图: {page['description']} ({page['url']})")
        driver.get(page['url'])
        
        # 等待页面加载完成
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, page['wait_element']))
        )
        
        # 等待一下确保页面完全渲染
        time.sleep(2)
        
        # 截图
        screenshot_path = f"promotion/screenshots/{page['name']}.png"
        driver.save_screenshot(screenshot_path)
        print(f"截图已保存: {screenshot_path}")
    except Exception as e:
        print(f"截图 {page['name']} 时出错: {str(e)}")

# 关闭浏览器
driver.quit()
print("所有截图完成!")