import re
import requests
from app.modules.wechat.wechat import WeChat


class MySender:
    def __init__(self, token=None):
        if not token:  # 如果 token 为空
            self.token = None
            self.channel = None
            self.init_success = False  # 标识初始化失败
        else:
            self.token = token
            self.channel = self.send_channel()  # 初始化时确定发送渠道
            self.first_text_sent = False  # 记录是否已经发送过纯文本消息
            self.init_success = True  # 标识初始化成功

    def send_channel(self):
        if self.token:
            # 优先判断是否为 WeChat 渠道
            if self.token == "WeChat":
                return "WeChat"

            letters_only = ''.join(re.findall(r'[A-Za-z]', self.token))
            # 判断其他推送渠道
            if self.token.startswith("SCT"):
                return "ServerChan"
            elif letters_only.isupper():
                return "AnPush"
            else:
                return "PushPlus"
        return None

    # 标题，内容，图片，是否强制发送
    def send(self, title, content, image=None, force_send=False, diy_chnnel=None):
        if not self.init_success:
            return  # 如果初始化失败，直接返回
        # 判断发送的内容类型
        contains_image = bool(image)  # 是否包含图片

        if not contains_image and not force_send:
            if self.first_text_sent:
                return
            else:
                self.first_text_sent = True
        # 根据发送渠道调用相应的发送方法
        if not diy_chnnel:  # 用户没有指定通知方式，使用初始化时确定的通知方式
            if self.channel == "WeChat":
                self.send_wechat(title, content, image)
            elif self.channel == "ServerChan":
                self.send_serverchan(title, content, image)
            elif self.channel == "AnPush":
                self.send_anpush(title, content, image)
            elif self.channel == "PushPlus":
                self.send_pushplus(title, content, image)
            else:
                raise ValueError("Unknown channel")
        else:
            if diy_chnnel == "WeChat":
                self.send_wechat(title, content, image)
            elif diy_chnnel == "ServerChan":
                self.send_serverchan(title, content, image)
            elif diy_chnnel == "AnPush":
                self.send_anpush(title, content, image)
            elif diy_chnnel == "PushPlus":
                self.send_pushplus(title, content, image)
            else:
                raise ValueError("Unknown channel")

    def send_wechat(self, title, content, contains_image):
        # WeChat发送逻辑
        wechat = WeChat()
        if contains_image:
            # 发送带图片的消息
            send_status = wechat.send_msg(
                title='企业微信登录二维码',
                # text=f"二维码刷新时间：{content}",
                image=contains_image,
                link=contains_image
            )
        # WeChat().send_msg(title = "点击扫描二维码登录企业微信",image='。。。',link='。。。')
        else:
            # 发送纯文本消息
            send_status = wechat.send_msg(
                title=title,
                text=f"{content}"
            )

    def send_serverchan(self, title, content, contains_image):
        if self.token.startswith('sctp'):
            match = re.match(r'sctp(\d+)t', self.token)
            if match:
                num = match.group(1)
                url = f'https://{num}.push.ft07.com/send/{self.token}.send'
            else:
                raise ValueError('Invalid sendkey format for sctp')
        else:
            url = f'https://sctapi.ftqq.com/{self.token}.send'

        if contains_image:
            params = {
                'title': title,
                'desp': f'![img]({contains_image})',
            }
        else:
            params = {
                'title': title,
                'desp': f'{content}',
                # **options
            }
        headers = {
            'Content-Type': 'application/json;charset=utf-8'
        }
        response = requests.post(url, json=params, headers=headers)
        result = response.json()

    def send_anpush(self, title, content, contains_image):
        if ',' in self.token:
            channel, token = self.token.split(',', 1)
        else:
            return
        url = f"https://api.anpush.com/push/{token}"
        # AnPush发送逻辑，带二维码的特殊处理
        if contains_image:
            payload = {
                "title": title,
                "content": f"<img src=\"{contains_image}\" width=\"100%\">",
                "channel": channel
            }
        else:
            payload = {
                "title": title,
                "content": f"{content}",
                "channel": channel
            }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        response = requests.post(url, headers=headers, data=payload)
        result = response.json()

    def send_pushplus(self, title, content, contains_image):
        pushplus_url = f"http://www.pushplus.plus/send/{self.token}"
        # PushPlus发送逻辑
        if contains_image:
            pushplus_data = {
                "title": title,
                "content": f"企业微信登录二维码<br/><img src='{contains_image}' />",
                "template": "html"
            }
        else:
            pushplus_data = {
                "title": title,
                "content": f"{content}",
                "template": "html"
            }
        response = requests.post(pushplus_url, json=pushplus_data)
        result = response.json()

    def reset_limit(self):
        """解除限制，允许再次发送纯文本消息"""
        self.first_text_sent = False
