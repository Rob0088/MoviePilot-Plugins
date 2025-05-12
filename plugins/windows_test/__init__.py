
from app.core.event import eventmanager, Event
import re
import time
import requests
import io

from datetime import datetime, timedelta
import pytz
from typing import Optional
from app.schemas.types import EventType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.log import logger
from app.plugins import _PluginBase
from app.core.config import settings

try:
    from selenium import webdriver
except ImportError:
    logger.info("未安装 selenium，请使用 pip install selenium 安装。")
    # exit(1)

class DynamicWeChat(_PluginBase):
    # 插件名称
    plugin_name = "修改企业微信可信IP_windows"
    # 插件描述
    plugin_desc = "以？结尾发给企业微信应用。如：110301？"
    # 插件图标
    plugin_icon = "Wecom_A.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "RamenRa"
    # 作者主页
    author_url = "https://github.com/RamenRa/MoviePilot-Plugins"
    # 插件配置项ID前缀
    plugin_config_prefix = "windows_test_"
    # 加载顺序
    plugin_order = 47
    # 可使用的用户级别


    # 如果成功导入 selenium，继续打开百度
    try:
        driver = webdriver.Chrome()
        driver.get("https://www.baidu.com")
        time.sleep(10)
        driver.quit()  # 关闭浏览器
        logger.info(f"浏览器已关闭。")
    except Exception as e:
        logger.info(f"打开百度失败，错误信息：{e}")
