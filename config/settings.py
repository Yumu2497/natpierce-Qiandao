import os
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass

# 加载 .env 文件
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


@dataclass
class Config:
    """签到脚本配置类"""
    
    # 网站配置
    BASE_URL: str = "https://www.natpierce.cn"
    SIGN_IN_URL: str = "https://www.natpierce.cn/pc/sign/index.html"
    
    # 登录配置 - 从环境变量读取
    USERNAME: str = os.getenv("SIGN_IN_USERNAME", "")
    PASSWORD: str = os.getenv("SIGN_IN_PASSWORD", "")
    
    # 超时配置
    PAGE_LOAD_TIMEOUT: int = 30000  # 页面加载超时（毫秒）
    WAIT_TIMEOUT: int = 10000  # 等待元素超时（毫秒）
    
    # 滑块验证配置
    SLIDER_RETRY_COUNT: int = 5  # 滑块验证重试次数
    SLIDER_OFFSET_RANGE: int = 5  # 滑块偏移容错范围（像素）
    
    # 浏览器配置
    # 先从 .env/环境变量读取，如果没有设置则默认为 True（无头模式）
    HEADLESS: bool = os.getenv("HEADLESS", "True").lower() in ("true", "1", "yes")
    WINDOW_WIDTH: int = 1920
    WINDOW_HEIGHT: int = 1080
    
    # 签到按钮选择器
    SIGN_IN_BUTTON_SELECTOR: str = "#qiandao"
    
    # 登录表单选择器（根据实际页面HTML）
    USERNAME_INPUT_SELECTOR: str = "#username"
    PASSWORD_INPUT_SELECTOR: str = "#password"
    LOGIN_BUTTON_SELECTOR: str = "div.login_btn"
    
    # 滑块验证选择器（网易验证码 necaptcha）
    SLIDER_CONTAINER_SELECTOR: str = "div[class*='yidun'], div[class*='captcha'], iframe[src*='necaptcha']"
    SLIDER_BUTTON_SELECTOR: str = "div.yidun_slider"
    SLIDER_BG_IMAGE_SELECTOR: str = "img.yidun_bgimg, canvas.yidun_bgimg"
    SLIDER_GAP_IMAGE_SELECTOR: str = "img.yidun_fbimg, canvas.yidun_fbimg"
    
    def validate(self) -> bool:
        """验证配置是否完整"""
        if not self.USERNAME or not self.PASSWORD:
            raise ValueError("请设置 SIGN_IN_USERNAME 和 SIGN_IN_PASSWORD 环境变量")
        return True
