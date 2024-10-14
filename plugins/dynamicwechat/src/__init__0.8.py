from app.core.event import eventmanager, Event
import re
import time
import requests
from datetime import datetime, timedelta
import pytz
# from playwright.sync_api import, Page
from typing import Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.schemas.types import EventType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.log import logger
from app.plugins import _PluginBase
from app.core.config import settings
# import dokcer_helper

class DynamicWeChat(_PluginBase):
    # 插件名称
    plugin_name = "修改企业微信可信IP"
    # 插件描述
    plugin_desc = "需要额外部署selenium/standalone-chrome容器。支持需要验证码的场景，注意验证码需要以？结尾。如：110301？"
    # 插件图标
    plugin_icon = "Wecom_A.png"
    # 插件版本
    plugin_version = "0.8.0"
    # 插件作者
    plugin_author = "RamenRa"
    # 作者主页
    author_url = "https://github.com/RamenRa/DynamicWeChat"
    # 插件配置项ID前缀
    plugin_config_prefix = "dynamicwechat_"
    # 加载顺序
    plugin_order = 50
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled = False  # 开关
    _cron = None
    _onlyonce = False
    # IP更改成功状态,防止检测IP改动但cookie失效的时候_current_ip_address已经更新成新IP导致后面刷新cookie也没有更改企微IP
    _ip_changed = False
    _forced_update = False

    #匹配ip地址的正则
    _ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    # 获取ip地址的网址列表
    _ip_urls = ["https://myip.ipip.net", "https://ddns.oray.com/checkip", "https://ip.3322.net", "https://4.ipw.cn"]
    # 当前ip地址
    _current_ip_address = '0.0.0.0'
    #企业微信登录
    _wechatUrl='https://work.weixin.qq.com/wework_admin/loginpage_wx?from=myhome'
    #检测间隔时间,默认10分钟
    _refresh_cron = '*/10 * * * *'
    # _urls = []
    _helloimg_s_token = ""
    _pushplus_token = ""
    _standalone_chrome_address = "http://192.168.1.0:4444/wd/hub"
    # _qrc_flag = ""

    text = ""
    user_id = ""
    channel = ""


    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None

    def init_plugin(self, config: dict = None):
        # 清空配置
        self._wechatUrl = 'https://work.weixin.qq.com/wework_admin/loginpage_wx?from=myhome'
        # self._urls = []
        self._helloimg_s_token = ''
        self._pushplus_token = ''
        self._standalone_chrome_address = "http://192.168.1.0:4444/wd/hub"
        self._ip_changed = True
        self._forced_update = False
        self._current_ip_address = self.get_ip_from_url(self._ip_urls[0])
        logger.info(f"当前公网 IP: {self._current_ip_address}")
        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._onlyonce = config.get("onlyonce")
            self._wechatUrl = config.get("wechatUrl")
            self._current_ip_address = config.get("current_ip_address")
            self._pushplus_token = config.get("pushplus_token")
            self._helloimg_s_token = config.get("helloimg_s_token")
            self._forced_update = config.get("forced_update")
            self._standalone_chrome_address = config.get("standalone_chrome_address")
            self._ip_changed = config.get("ip_changed")

        # 停止现有任务
        self.stop_service()
        if self._enabled or self._onlyonce:
            # 定时服务
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            # 运行一次定时服务
            if self._onlyonce or self._forced_update:
                logger.info("立即检测公网IP")
                self._scheduler.add_job(func=self.check, trigger='date',
                                        run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                                        name="检测公网IP")   # 添加任务
                # 关闭一次性开关
                self._onlyonce = False
            # 启动任务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()
                if self._forced_update:
                    time.sleep(4)
                    self._forced_update = False
        self.__update_config()

    @eventmanager.register(EventType.PluginAction)
    def check(self, event: Event = None):
        """
        检测函数
        """
        if not self._enabled:
            logger.error("插件未开启")
            return

        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "dynamicwechat":
                return
            logger.info("收到命令，开始检测公网IP ...")
            self.post_message(channel=event.event_data.get("channel"),
                              title="开始检测公网IP ...",
                              userid=event.event_data.get("user"))

        logger.info("开始检测公网IP")
        if self.CheckIP():
            self.ChangeIP()
            self.__update_config()

        logger.info("检测公网IP完毕")
        if event:
            self.post_message(channel=event.event_data.get("channel"),
                              title="检测公网IP完毕",
                              userid=event.event_data.get("user"))

    def CheckIP(self):
        for url in self._ip_urls:
            ip_address = self.get_ip_from_url(url)
            if ip_address != "获取IP失败" and ip_address:
                logger.info(f"IP获取成功: {url}: {ip_address}")
                break
            else:
                logger.error(f"请求网址失败: {url}")

        # 如果所有 URL 请求失败
        if ip_address == "获取IP失败" and not ip_address:
            logger.error("获取IP失败 不操作IP")
            return False

        if self._forced_update:
            logger.info("强制更新IP")
            self._current_ip_address = ip_address
            return True
        elif not self._ip_changed: # 上次修改IP失败
            logger.info("上次IP修改IP没有成功 继续尝试修改IP")
            self._current_ip_address = ip_address
            return True

        # 检查 IP 是否变化
        if ip_address != self._current_ip_address:
            logger.info("检测到IP变化")
            self._current_ip_address = ip_address
            # self._ip_changed = False
            return True
        else:
            # logger.info("公网IP未变化")
            # logger.info("self._forced_update", self._forced_update)
            return False

    def get_ip_from_url(self, url):
        try:
            # 发送 GET 请求
            response = requests.get(url)
            # 检查响应状态码是否为 200
            if response.status_code == 200:
                # 解析响应 JSON 数据并获取 IP 地址
                ip_address = re.search(self._ip_pattern, response.text)
                if ip_address:
                    return ip_address.group()
                else:
                    return "获取IP失败"
            else:
                return "获取IP失败"
        except Exception as e:
            logger.warning(f"{url}获取IP失败,Error: {e}")
            # return "获取IP失败"
    def find_qrc(self, driver):
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            iframe_element = driver.find_element(By.TAG_NAME, "iframe")
            driver.switch_to.frame(iframe_element)  # 切换到 iframe
        except Exception as e:
            pass

        try:
            img_elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "img"))
            )
        except Exception as e:
            pass

        qr_code_element = None
        for img in img_elements:
            if 'qrcode' in img.get_attribute('src'):
                qr_code_element = img
                break  # 找到二维码元素后退出循环
        if qr_code_element:
            # 保存二维码图片
            qr_code_url = qr_code_element.get_attribute('src')
            qr_code_data = requests.get(qr_code_url).content
            with open("/app/qr_code.png", 'wb') as f:
                f.write(qr_code_data)
            return True
        else:
            return False

    def ChangeIP(self):
        logger.info("开始请求企业微信管理更改可信IP")
        driver = None
        # 解析 Cookie 字符串为字典
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--headless')  # 无头模式运行
            # chrome_options.add_argument('--no-sandbox')
            # chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--lang=zh-CN')  # 设置为中文
            # driver = webdriver.Chrome(options=chrome_options)  # 根据需要选择 Chrome 或其他浏览器
            # dokcer_helper.check_selenium_ready(self._standalone_chrome_address)
            status_code = requests.get(self._standalone_chrome_address.replace('wd/hub', 'ui')).status_code
            if not status_code == 200:
                logger.error(f"无法连接到 Selenium 服务器: {status_code} 程序终止")
                self._ip_changed = False
                return
            driver = webdriver.Remote(command_executor=self._standalone_chrome_address, options=chrome_options)
            driver.get(self._wechatUrl)
            time.sleep(2)
            if self.find_qrc(driver):
                img_src, refuse_time = self.upload_image("/app/qr_code.png")
                self.send_pushplus_message(refuse_time, f"企业微信登录二维码<br/><img src='{img_src}' />")
                logger.info("二维码已经发送，等待用户 60 秒内扫码登录")
                logger.info("如收到短信验证码请以？结束，发送到<企业微信应用> 如： 110301？")
                time.sleep(60)  # 等待用户扫码
                login_status = self.check_login_status(driver)
                if login_status:
                    self.click_app_management_button(driver)
                    self.enter_public_ip(driver)
            else:
                logger.info("未找到二维码图片。")
                self._ip_changed = False
                return
        except Exception as e:
            logger.error(f"更改可信IP失败: {e}")
        finally:
            logger.info("----------------------本次任务结束----------------------")
            if driver:
                driver.quit()

    def enter_public_ip(self, driver):
        time.sleep(2)
        try:
            # 找到文本框并输入 IP 地址
            ip_textarea = driver.find_element(By.XPATH,
                                              "//textarea[@class='js_ipConfig_textarea']")
            ip_textarea.clear()
            ip_textarea.send_keys(self._current_ip_address)
            logger.info("已输入公网IP：" + self._current_ip_address)
            time.sleep(3)
            # 点击确定按钮
            confirm_button = driver.find_element(By.XPATH,
                                                 "//a[@class='qui_btn ww_btn ww_btn_Blue js_ipConfig_confirmBtn']")

            confirm_button.click()
            logger.info("已点击确定按钮")
            time.sleep(3)  # ???
            self._ip_changed = True

        except Exception as e:
            # print("未能找到或输入文本框或者确认按钮:", e)
            logger.error(f"未能找到或输入文本框或者确认按钮：{e}")
#
    def check_login_status(self, driver):
        try:
            logger.info("检查是否需要进行短信验证...")
            time.sleep(3)
            captcha_panel = driver.execute_script("return document.querySelector('.receive_captcha_panel');")
            if captcha_panel:  # 出现了短信验证界面
                logger.info("需要短信验证 收到的短信验证码：" + self.text)
                captcha_input = driver.find_element(By.CSS_SELECTOR, ".inner_input")
                captcha_input.send_keys(self.text)      # debug模拟验证码
                # logger.info("已输入验证码")
                confirm_button = driver.find_element(By.CSS_SELECTOR, ".confirm_btn")
                confirm_button.click()
                success_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "check_corp_info"))
                )
                # logger.info("等待短信验证完成")
                if success_element:
                    logger.info("登录成功！")
                    return True
            elif self.find_qrc(driver):     # 二维码依然存在于登录界面
                logger.error(f"用户没有扫码/发送验证码或者登录失败")
                self._ip_changed = False
                return False
            else:
                logger.info("无需短信验证码")
                success_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "check_corp_info"))
                )
                if success_element:
                    logger.info("登录成功！")
                    return True
        except Exception as e:
            pass
            # print(f"检查新的短信安全验证时出错: {e}")
            # logger.error(f"用户没有扫码/发送验证码或者登录失败,  ")
            # self._ip_changed = False
            # return
    def click_button(self, driver, xpath, button_name):
        """
        查找并点击指定按钮，并检测是否成功找到该按钮。

        :param driver: Selenium WebDriver 对象
        :param xpath: 按钮的 XPath
        :param button_name: 按钮的名称，用于输出提示信息
        :return: bool, 如果成功找到并点击按钮则返回 True，反之返回 False
        """
        try:
            # 等待按钮出现并可点击
            button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            button.click()
            logger.info(f"已点击 '{button_name}' 按钮")
            return True
        except Exception as e:
            # print(f"未能找到或点击 '{button_name}' 按钮: {e} 终止")
            logger.error(f"未能找到或点击 '{button_name}' 按钮: {e}  ")
            self._ip_changed = False
            # return

    def click_app_management_button(self, driver):
        """
        查找并点击页面中的 '应用管理' 按钮，然后点击 'MoviePilot' 按钮，最后点击 '配置' 按钮。
        """
        time.sleep(3)

        # 按钮的选择器和名称
        buttons = [
            ("//span[@class='frame_nav_item_title' and text()='应用管理']", "应用管理"),
            ("//div[@class='app_index_item_title ' and contains(text(), 'MoviePilot')]", "MoviePilot"),
            ("//div[contains(@class, 'js_show_ipConfig_dialog')]//a[contains(@class, '_mod_card_operationLink') and text()='配置']", "配置")
        ]

        # 依次点击每个按钮
        for xpath, name in buttons:
            if not self.click_button(driver, xpath, name):
                # print(f"未能找到 '{name}' 按钮，终止")
                logger.error(f"未能找到 '{name}' 按钮，终止")
                self._ip_changed = False
                return  # 取消exit 如果未能找到按钮，提前结束操作


    def send_pushplus_message(self, title, content):
        pushplus_url = f"http://www.pushplus.plus/send/{self._pushplus_token}"
        pushplus_data = {
            "title": title,
            "content": content,
            "template": "html"
        }
        # if wait_time > 2:
        #     # time.sleep(wait_time)
        #     logger.info(f"pushplus API 调用次数限制，本次不发送 至少间隔 {wait_time} 秒")
        # else:
        response = requests.post(pushplus_url, json=pushplus_data)
        # return response

    def upload_image(self, file_path="qr_code.png", permission=1, strategy_id=1, album_id=1):
        helloimg_token = "Bearer " + self._helloimg_s_token
        helloimg_url = "https://www.helloimg.com/api/v1/upload"
        headers = {
            "Authorization": helloimg_token,
            "Accept": "application/json",
        }
        files = {
            "file": open(file_path, "rb")
        }
        expired_at = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        helloimg_data = {
            "token": "你的临时上传 Token",  # 确保这里的 token 是有效的
            "permission": permission,
            "strategy_id": strategy_id,
            "album_id": album_id,
            "expired_at": expired_at
        }
        refuse_time = (datetime.now() + timedelta(seconds=110)).strftime("%Y-%m-%d %H:%M:%S")

        # logger.info(f"准备上传图片，使用的Token: {helloimg_token}")
        response = requests.post(helloimg_url, headers=headers, files=files, data=helloimg_data)
        # 打印响应内容
        # logger.info(f"上传响应: {response.text}")

        # 检查响应内容是否符合预期
        try:
            response_data = response.json()
            if not response_data['status']:
                if response_data['message'] == "Unauthenticated.":
                    logger.error("Token失效，无法上传图片。请检查你的上传Token。")
                    logger.info(f"使用的Token: {helloimg_token}  ")
                    self._ip_changed = False
                    return
                else:
                    logger.error(f"上传到图床失败: {response_data['message']}  ")
                    self._ip_changed = False
                    return

            img_src = response_data['data']['links']['html']
            # logger.info(f"图片上传成功，链接：{img_src}")
            return img_src.split('"')[1], refuse_time  # 提取 img src

        except KeyError as e:
            logger.error(f"上传图片时解析响应失败: {e}, 响应内容: {response_data}")
            logger.info(f"本次操作终止")
            self._ip_changed = False
            return

    def __update_config(self):
        """
        更新配置
        """
        self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "wechatUrl": self._wechatUrl,
            "current_ip_address": self._current_ip_address,
            "ip_changed": self._ip_changed,
            "forced_update": self._forced_update,
            "helloimg_s_token": self._helloimg_s_token,
            "pushplus_token": self._pushplus_token,
            "standalone_chrome_address": self._standalone_chrome_address
        })

    def get_state(self) -> bool:
        return self._enabled

    from typing import Tuple, List, Dict, Any

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，只保留必要的配置项，并添加 token 配置。
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即检测一次',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'forced_update',
                                            'label': '强制更新',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '检测周期',
                                            'placeholder': '0 * * * *'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'wechatUrl',
                                            'label': '登录页面',
                                            'rows': 1,
                                            'placeholder': '企业微信应用的管理网址 多个地址用,分隔'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    # 将 pushplus_token 和 helloimg_s_token 放在同一行
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'pushplus_token',
                                            'label': 'pushplus_token',
                                            'rows': 1,
                                            'placeholder': '请输入 pushplus_token'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'helloimg_s_token',
                                            'label': 'helloimg_s_token',
                                            'rows': 1,
                                            'placeholder': '请输入 helloimg_token'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'standalone_chrome_address',
                                            'label': 'standalone_chrome_address',
                                            'placeholder': '请输入 selenium/standalone-chrome容器的地址'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': 'selenium-chrome 一键部署命令：docker run -d --name selenium-chrome -p 4444:4444 --shm-size="1g" selenium/standalone-chrome:latest'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '* 强制更新按钮和立即检测按钮一样都是一次性按钮。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "cron": "",
            "onlyonce": False,
            "forceUpdate": False,
            "wechatUrl": "",
            "pushplus_token": "",
            "helloimg_token": "",
            "standalone_chrome_address": ""
        }

    def get_page(self) -> List[dict]:
        pass

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    @eventmanager.register(EventType.UserMessage)
    def talk(self, event: Event):
        """
        监听用户消息
        """
        if not self._enabled:
            return
        self.text = event.event_data.get("text")
        self.user_id = event.event_data.get("userid")
        self.channel = event.event_data.get("channel")
        if self.text and len(self.text) == 7:
            logger.info(f"收到验证码：{self.text}")
        else:
            logger.info(f"收到消息：{self.text}")

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        if self._enabled and self._cron:
            logger.info(f"{self.plugin_name}定时服务启动，时间间隔 {self._cron} ")
            return [{
                "id": self.__class__.__name__,
                "name": f"{self.plugin_name}服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.check,
                "kwargs": {}
            }]

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown()
                    self._event.clear()
                self._scheduler = None
        except Exception as e:
            logger.error(str(e))
