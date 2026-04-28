"""
自动签到脚本
使用 Playwright 和 ddddocr 实现自动登录、滑块验证和签到
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page
from config.settings import Config
from slider_solver import SliderCaptchaSolver

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class SignInBot:
    """签到机器人"""
    
    def __init__(self):
        self.config = Config()
        self.config.validate()
        self.page: Page = None
    
    async def init_browser(self, playwright):
        """初始化浏览器"""
        video_dir = Path("debug") / "playwright-videos"
        video_dir.mkdir(parents=True, exist_ok=True)

        browser = await playwright.chromium.launch(
            headless=self.config.HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--window-size=1280,720",
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
            record_video_dir=str(video_dir),
            record_video_size={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # 添加反检测脚本
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.page = await context.new_page()
        return browser, context
    
    async def navigate_to_signin(self):
        """导航到签到页面"""
        print(f"[导航] 正在访问: {self.config.SIGN_IN_URL}")
        
        try:
            await self.page.goto(
                self.config.SIGN_IN_URL,
                wait_until="domcontentloaded",
                timeout=self.config.PAGE_LOAD_TIMEOUT
            )
            await self.page.wait_for_load_state("networkidle")
            print("[导航] 页面加载完成")
        except Exception as e:
            print(f"[导航] 页面加载出错: {e}")
            raise
    
    async def check_login_status(self) -> bool:
        """检查登录状态"""
        current_url = self.page.url
        print(f"[登录检查] 当前URL: {current_url}")
        
        # 如果URL包含login，说明需要登录
        if "login" in current_url.lower():
            print("[登录检查] 未登录，需要跳转到登录页面")
            return False
        
        print("[登录检查] 已登录")
        return True
    
    async def login(self):
        """执行登录"""
        print("[登录] 正在执行登录...")
        
        # 等待登录表单出现
        await self.page.wait_for_selector(
            self.config.USERNAME_INPUT_SELECTOR,
            timeout=self.config.WAIT_TIMEOUT
        )
        
        # 输入用户名
        username_input = await self.page.query_selector(self.config.USERNAME_INPUT_SELECTOR)
        await username_input.click()
        await username_input.fill(self.config.USERNAME)
        print(f"[登录] 已输入用户名")
        
        # 输入密码
        password_input = await self.page.query_selector(self.config.PASSWORD_INPUT_SELECTOR)
        await password_input.click()
        await password_input.fill(self.config.PASSWORD)
        print(f"[登录] 已输入密码")
        
        # 点击登录按钮
        login_btn = await self.page.query_selector(self.config.LOGIN_BUTTON_SELECTOR)
        
        # 点击登录按钮并等待页面加载
        async with self.page.expect_navigation(wait_until="domcontentloaded", timeout=self.config.PAGE_LOAD_TIMEOUT) as navigation_info:
            await login_btn.click()
        print("[登录] 已点击登录按钮，等待页面加载...")
        
        # 等待页面完全加载
        await self.page.wait_for_load_state("networkidle", timeout=self.config.PAGE_LOAD_TIMEOUT)
        print("[登录] 页面加载完成")
        
        # 检查是否出现滑块验证
        try:
            slider_container = await self.page.wait_for_selector(
                self.config.SLIDER_CONTAINER_SELECTOR, 
                timeout=3000
            )
            if slider_container:
                print("[登录] 检测到滑块验证，开始处理...")
                solver = SliderCaptchaSolver(self.page, self.config)
                success = await solver.solve()
                
                if not success:
                    raise Exception("滑块验证失败")
        except Exception:
            # 没有滑块验证，可能直接登录成功了
            print("[登录] 未检测到滑块验证")
        
        # 等待登录成功后的跳转
        print("[登录] 等待登录成功...")
        try:
            await self.page.wait_for_url(
                "**/sign/**",
                timeout=self.config.PAGE_LOAD_TIMEOUT
            )
            print("[登录] 登录成功，已跳转到签到页面")
        except Exception:
            # 可能已经在签到页面了
            current_url = self.page.url
            print(f"[登录] 当前页面: {current_url}")
    
    async def click_signin_button(self):
        """点击签到按钮"""
        print("[签到] 正在查找签到按钮...")
        
        # 尝试多种选择器
        selectors = [
            self.config.SIGN_IN_BUTTON_SELECTOR,
            "button:has-text('签到')",
            ".sign-btn",
            "#signin",
            "#sign-in",
            "a:has-text('签到')",
        ]
        
        sign_btn = None
        for selector in selectors:
            try:
                sign_btn = await self.page.wait_for_selector(
                    selector,
                    timeout=5000
                )
                if sign_btn:
                    print(f"[签到] 找到签到按钮: {selector}")
                    break
            except Exception:
                continue
        
        if not sign_btn:
            print("[签到] 未找到签到按钮，尝试在页面中搜索...")
            # 尝试通过文本查找
            all_buttons = await self.page.query_selector_all("button, a, div")
            for btn in all_buttons:
                text = await btn.inner_text()
                if "签到" in text:
                    sign_btn = btn
                    print(f"[签到] 通过文本找到按钮: {text}")
                    break
        
        if not sign_btn:
            raise Exception("未找到签到按钮")
        
        # 检查是否已经签到
        btn_text = await sign_btn.inner_text()
        if "已签到" in btn_text or "重复签到" in btn_text:
            print(f"[签到] 今天已经签到过了 ({btn_text})")
            return True
        
        # 点击签到按钮
        await sign_btn.click()
        print("[签到] 已点击签到按钮")
        
        # 等待滑块验证出现（签到可能需要滑块验证）
        await self.page.wait_for_timeout(1000)
        
        try:
            slider_container = await self.page.wait_for_selector(
                self.config.SLIDER_CONTAINER_SELECTOR,
                timeout=3000
            )
            if slider_container:
                print("[签到] 检测到滑块验证，开始处理...")
                solver = SliderCaptchaSolver(self.page, self.config)
                success = await solver.solve()
                
                if not success:
                    raise Exception("签到滑块验证失败")
                
                # 滑块验证完成后等待结果
                await self.page.wait_for_timeout(1500)
        except TimeoutError:
            # 没有滑块验证，可能直接签到成功或者已经签到过了
            print("[签到] 未检测到滑块验证")
        except Exception as e:
            # 滑块验证失败，重新抛出
            raise
        
        # 截图保存签到结果
        screenshot_path = f"signin_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await self.page.screenshot(path=screenshot_path)
        print(f"[签到] 签到结果截图已保存: {screenshot_path}")
        
        return True
    
    async def run(self):
        """运行签到流程"""
        print("=" * 50)
        print(f"签到脚本启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)
        
        async with async_playwright() as playwright:
            browser, context = await self.init_browser(playwright)
            
            try:
                # 1. 导航到签到页面
                await self.navigate_to_signin()
                
                # 2. 检查登录状态
                is_logged_in = await self.check_login_status()
                
                if not is_logged_in:
                    # 3. 执行登录
                    await self.login()
                    
                    # 登录后重新导航到签到页面
                    print("[导航] 登录完成，导航到签到页面...")
                    await self.navigate_to_signin()
                
                # 4. 执行签到
                await self.click_signin_button()
                
                print("\n" + "=" * 50)
                print("签到完成!")
                print("=" * 50)
                
            except Exception as e:
                logger.error(f"签到失败: {e}")
                # 出错时截图
                error_screenshot = f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await self.page.screenshot(path=error_screenshot)
                logger.error(f"错误截图已保存: {error_screenshot}")
            finally:
                # 关闭浏览器
                await context.close()
                await browser.close()


async def main():
    """主函数"""
    bot = SignInBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
