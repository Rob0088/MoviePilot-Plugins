import time
# import traceback
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import TimeoutException


def login(driver, refresh_interval, text, userid):
    while True:
        try:
            print("等待正常登录状态...")
            success_element = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, "check_corp_info"))
            )
            if success_element:
                print("登录成功！")
                break
        except Exception as e:
            print("未能检测到登录状态:", e)

        # 检查短信安全验证的标识元素
        try:
            # 等待短信安全验证面板出现
            captcha_panel = driver.execute_script("return document.querySelector('.receive_captcha_panel');")
            if captcha_panel:
                print("请发送手机验证码到企业微信应用，完成验证。")
                # 等待验证通过
                time.sleep(3)   # 等待用户发送验证码
                captcha_input = driver.find_element(By.CSS_SELECTOR, ".inner_input")  # 修复此行
                captcha_input.send_keys(text)      # debug模拟验证码
                confirm_button = driver.find_element(By.CSS_SELECTOR, ".confirm_btn")  # 修复此行
                confirm_button.click()
                WebDriverWait(driver, refresh_interval).until(
                    EC.presence_of_element_located((By.ID, "check_corp_info"))
                )
                print("验证通过，登录成功！")
                break  # 成功登录后退出循环

        except Exception as e:
            print(f"检查新的短信安全验证时出错: {e}")
    return True

# 刷新页面
# try:
#     # driver.switch_to.default_content()  # 切换回主页面
#     driver.refresh()
#     time.sleep(3)  # 等待页面刷新
# except Exception as e:
#     print("刷新页面时出错:", e)
#     break


# captcha_input = driver.find_element_by_css_selector(".inner_input")
# captcha_input.send_keys("你收到的验证码")
#
# confirm_button = driver.find_element_by_css_selector(".confirm_btn")
# confirm_button.click()

# <span class="receive_captcha_highlight">199****6689</span>
# "//span[@class='frame_nav_item_title' and text()='应用管理']", "应用管理"

# "//span[@class='receive_captcha_highlight']"