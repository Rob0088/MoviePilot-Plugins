import requests
from datetime import datetime, timedelta
import time
# 全局变量
helloimg_s_token = "366|PufEe2HSvPbdHyGttuWvtp4jEVKNahFq2jRaYYfU"
pushplus_token = "6bf81ef22808436283c19a53a83919da"
last_run_time = 0  # 用于记录上次运行的时间


def send_pushplus_message(title, content):
    def can_run():
        global last_run_time
        current_time = time.time()
        if current_time - last_run_time >= 180:  # 检查是否已过180秒
            last_run_time = current_time
            return 1
        else:
            return int(180 - (current_time - last_run_time))

    wait_time = can_run()


    pushplus_url = f"http://www.pushplus.plus/send/{pushplus_token}"
    pushplus_data = {
        "title": title,
        "content": content,
        "template": "html"
    }
    if wait_time > 2:
        # print(f"API 调用次数限制，还需等待 {wait_time} 秒。")
        print(f"API 调用次数限制，本次不发送")
        # time.sleep(wait_time)
    else:
        response = requests.post(pushplus_url, json=pushplus_data)
        # return response

def upload_image(file_path, token=helloimg_s_token, permission=1, strategy_id=1, album_id=1):
    helloimg_token = "Bearer " + token
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
        "token": "你的临时上传 Token",  # 替换为你的临时上传 Token
        "permission": permission,
        "strategy_id": strategy_id,
        "album_id": album_id,
        "expired_at": expired_at
    }
    refuse_time = (datetime.now() + timedelta(seconds=110)).strftime("%Y-%m-%d %H:%M:%S")
    response = requests.post(helloimg_url, headers=headers, files=files, data=helloimg_data)
    img_src = response.json()['data']['links']['html']
    return img_src.split('"')[1], refuse_time  # 提取 img src

# 示例调用
# img_src, refuse_time = upload_image("qr_code.png", helloimg_s_token)
# push_response = send_pushplus_message(refuse_time, f"企业微信登录二维码<br/><img src='{img_src}' />")

