import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from pushmsg import send_pushplus_message, upload_image
from login_funtion import login


class DynamicWeChatHelper:
    def __init__(self):
        self.login_url = "https://work.weixin.qq.com/wework_admin/loginpage_wx?from=myhome"
        # 设置 Chrome 浏览器的选项
        self.chrome_options = webdriver.ChromeOptions()
        self.chrome_options.add_argument('--headless')  # 无头模式运行
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.urls = [
            "https://4.ipw.cn/",
            # "https://api.ipify.org",          # 注意不要挂代理！！！
            # "https://checkip.amazonaws.com",
            # "https://ifconfig.me"
        ]

    def check_public_ip(self):
        for url in self.urls:
            for attempt in range(2):  # 最大重试 2 次
                try:
                    response = requests.get(url, timeout=5)
                    response.raise_for_status()  # 检查请求是否成功
                    public_ip = response.text.strip()
                    print(f"当前公网 IP: {public_ip}")
                    return public_ip
                except (requests.RequestException, Exception) as e:
                    print(f"尝试从 {url} 获取公网 IP 失败: {e}")
                    time.sleep(5)  # 每次重试间隔 5 秒
        print("所有尝试均失败，无法获取公网 IP")
        return None



