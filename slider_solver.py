import io
import random
import base64
import logging
from datetime import datetime
from pathlib import Path
from PIL import Image
from playwright.async_api import Page
import ddddocr

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class SliderCaptchaSolver:
    """滑块验证码解决器 - 适配网易验证码(necaptcha)"""
    
    def __init__(self, page: Page, config):
        self.page = page
        self.config = config
        self.slide_ocr = ddddocr.DdddOcr(det=False, ocr=False)
    
    async def get_captcha_images(self) -> tuple[bytes, bytes]:
        """
        获取验证码图片
        返回: (背景图片字节, 滑块图片字节)
        """
        # 等待验证码出现
        await self.page.wait_for_timeout(1500)
        
        bg_bytes = None
        slider_bytes = None
        
        # 从固定的class获取
        try:
            # 背景图: img.yidun_bg-img
            bg_img = await self.page.query_selector("img.yidun_bg-img")
            if bg_img:
                bg_src = await bg_img.get_attribute("src")
                if bg_src:
                    logger.info(f"[图片获取] 背景图URL: {bg_src}")
                    bg_bytes = await self._download_image(bg_src)
                    if bg_bytes:
                        logger.info(f"[图片获取] 背景图下载成功, 大小: {len(bg_bytes)} bytes")
        except Exception as e:
            logger.warning(f"[图片获取] 获取背景图失败: {e}")
        
        try:
            # 滑块图: img.yidun_jigsaw
            slider_img = await self.page.query_selector("img.yidun_jigsaw")
            if slider_img:
                slider_src = await slider_img.get_attribute("src")
                if slider_src:
                    logger.info(f"[图片获取] 滑块图URL: {slider_src}")
                    slider_bytes = await self._download_image(slider_src)
                    if slider_bytes:
                        logger.info(f"[图片获取] 滑块图下载成功, 大小: {len(slider_bytes)} bytes")
        except Exception as e:
            logger.warning(f"[图片获取] 获取滑块图失败: {e}")
        
        if not bg_bytes:
            raise Exception("无法获取验证码背景图片")
        
        if not slider_bytes:
            raise Exception("无法获取验证码滑块图")
        
        return bg_bytes, slider_bytes
    
    async def _download_image(self, src: str) -> bytes:
        """下载图片"""
        if not src:
            return None
            
        if src.startswith("data:"):
            # base64图片
            base64_data = src.split(",")[1]
            return base64.b64decode(base64_data)
        elif src.startswith("http"):
            # URL图片 - 使用urllib直接下载，避免Playwright的流问题
            import urllib.request
            import ssl
            
            try:
                # 禁用SSL验证（某些网站证书可能有问题）
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                req = urllib.request.Request(src)
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                
                with urllib.request.urlopen(req, context=ssl_context, timeout=10) as response:
                    data = response.read()
                    
                # 验证图片完整性
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(data))
                img.verify()  # 验证图片格式
                
                # 重新打开（verify会关闭文件）
                img = Image.open(io.BytesIO(data))
                img.load()  # 加载图片数据
                
                logger.info(f"[图片下载] 下载成功, 尺寸: {img.size}")
                return data
            except Exception as e:
                logger.error(f"[图片下载] 失败: {e}")
                return None
        else:
            return None
    
    async def get_captcha_metrics(self) -> dict:
        """获取验证码图片在页面上的实际渲染尺寸。"""
        bg_img = await self.page.query_selector("img.yidun_bg-img")
        if not bg_img:
            raise Exception("未找到验证码背景图元素")

        bg_metrics = await bg_img.evaluate("""
            (img) => ({
                width: img.getBoundingClientRect().width,
                height: img.getBoundingClientRect().height,
                naturalWidth: img.naturalWidth || 0,
                naturalHeight: img.naturalHeight || 0,
            })
        """)

        track = await self.page.query_selector("div.yidun_slider")
        track_metrics = None
        if track:
            track_metrics = await track.evaluate("""
                (el) => ({
                    width: el.getBoundingClientRect().width,
                    height: el.getBoundingClientRect().height,
                })
            """)

        return {
            "bg_width": bg_metrics["width"],
            "bg_height": bg_metrics["height"],
            "bg_natural_width": bg_metrics["naturalWidth"],
            "bg_natural_height": bg_metrics["naturalHeight"],
            "track_width": track_metrics["width"] if track_metrics else None,
            "track_height": track_metrics["height"] if track_metrics else None,
        }

    async def calculate_slide_distance(self, bg_bytes: bytes, slider_bytes: bytes) -> dict:
        """
        使用ddddocr计算需要滑动的距离
        返回: {"distance": int, "target_x": int, "target_y": int}
        """
        try:
            result = self.slide_ocr.slide_match(slider_bytes, bg_bytes)
            
            target_x = result.get("target_x", 0)
            target_y = result.get("target_y", 0)
            confidence = result.get("confidence", 0)
            
            slider_img = Image.open(io.BytesIO(slider_bytes))
            slider_width = slider_img.size[0]
            bg_img = Image.open(io.BytesIO(bg_bytes))
            bg_width = bg_img.size[0]
            metrics = await self.get_captcha_metrics()
            
            rendered_bg_width = metrics["bg_width"] or bg_width
            scale_ratio = rendered_bg_width / bg_width if bg_width else 1
            slide_distance = target_x * scale_ratio
            
            # 保存验证码图片用于调试
            self._save_captcha_debug(bg_bytes, [target_x, target_y, 0, 0])
            
            logger.info(f"[OCR识别] 缺口坐标: x={target_x}, y={target_y}, 置信度: {confidence:.4f}")
            logger.info(
                f"[OCR识别] 原图宽度: {bg_width}px, 页面渲染宽度: {rendered_bg_width:.2f}px, 缩放比: {scale_ratio:.4f}"
            )
            logger.info(
                f"[OCR识别] 滑块图片宽度: {slider_width}px, 滑轨宽度: {metrics['track_width']}"
            )
            logger.info(f"[OCR识别] 需要滑动距离: {slide_distance:.2f}px")
            
            return {
                "distance": max(0, slide_distance),
                "target_x": target_x,
                "target_y": target_y,
                "scale_ratio": scale_ratio,
            }
        except Exception as e:
            logger.error(f"[OCR识别] 失败: {e}")
            raise
    
    def _save_captcha_debug(self, bg_bytes: bytes, target: list):
        """保存验证码图片用于调试"""
        try:
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 保存背景图
            bg_path = debug_dir / f"captcha_bg_{timestamp}.jpg"
            with open(bg_path, "wb") as f:
                f.write(bg_bytes)
            logger.info(f"[调试] 背景图已保存: {bg_path}")
            
            # 保存带缺口标记的图片
            img = Image.open(io.BytesIO(bg_bytes))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            
            # 画矩形框标记缺口位置
            if len(target) >= 4:
                x, y, w, h = target[0], target[1], target[2], target[3]
                draw.rectangle([(x, y), (x + w, y + h)], outline="red", width=3)
                # 添加文字标注
                draw.text((x, y - 15), f"({x},{y})", fill="red")
            
            marked_path = debug_dir / f"captcha_marked_{timestamp}.png"
            img.save(marked_path)
            logger.info(f"[调试] 标记图已保存: {marked_path}")
            
        except Exception as e:
            logger.warning(f"[调试] 保存图片失败: {e}")

    async def save_page_debug(self, prefix: str):
        """保存当前页面截图，便于分析无头环境下的验证码状态。"""
        try:
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = debug_dir / f"{prefix}_{timestamp}.png"
            await self.page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"[调试] 页面截图已保存: {screenshot_path}")
        except Exception as e:
            logger.warning(f"[调试] 保存页面截图失败: {e}")

    def get_slide_track(self, distance: int) -> list[dict]:
        """
        生成模拟人类滑动轨迹
        返回: 轨迹点列表 [{"x": x, "y": y, "t": timestamp}, ...]
        """
        track = []
        current_x = 0
        current_y = 0
        time_offset = 0
        
        # 分阶段滑动：先快后慢
        mid_point = distance * 4 // 5
        
        # 加速阶段
        while current_x < mid_point:
            step = random.randint(5, 15)
            current_x += step
            if current_x > mid_point:
                current_x = mid_point
            
            time_offset += random.randint(10, 30)
            current_y = random.randint(-2, 2)
            track.append({"x": current_x, "y": current_y, "t": time_offset})
        
        # 减速阶段
        while current_x < distance:
            step = random.randint(1, 5)
            current_x += step
            if current_x > distance:
                current_x = distance
            
            time_offset += random.randint(20, 50)
            current_y = random.randint(-1, 1)
            track.append({"x": current_x, "y": current_y, "t": time_offset})
        
        # 最后稍微回退一点，模拟真实操作
        if random.random() > 0.5:
            back_steps = random.randint(1, 3)
            current_x -= back_steps
            time_offset += random.randint(10, 20)
            track.append({"x": current_x, "y": 0, "t": time_offset})
        
        return track
    
    async def find_slider_element(self):
        """查找滑块元素 - 适配网易验证码"""
        # 网易验证码滑块的确切选择器
        selectors = [
            "div.yidun_slider",                    # 主滑块
            "div[class*='yidun_slider']",          # 滑块容器
        ]
        
        for selector in selectors:
            slider = await self.page.query_selector(selector)
            if slider:
                print(f"[滑块验证] 找到滑块元素: {selector}")
                return slider
        
        # 如果没找到，尝试通过内部icon查找
        slider_icon = await self.page.query_selector("span.yidun_slider__icon")
        if slider_icon:
            # 返回父元素（实际的滑块容器）
            parent = await self.page.evaluate("""
                (icon) => icon.parentElement
            """, slider_icon)
            if parent:
                print("[滑块验证] 通过icon找到滑块元素")
                return parent
        
        return None
    
    async def perform_slide(self, track: list[dict]) -> bool:
        """
        执行滑动操作
        返回: 是否成功
        """
        # 定位滑块按钮
        slider_btn = await self.find_slider_element()
        
        if not slider_btn:
            print("[滑块验证] 未找到滑块元素")
            return False
        
        # 获取滑块位置
        slider_box = await slider_btn.bounding_box()
        start_x = slider_box["x"] + slider_box["width"] / 2
        start_y = slider_box["y"] + slider_box["height"] / 2
        
        # 鼠标按下
        await self.page.mouse.move(start_x, start_y, steps=random.randint(8, 15))
        await self.page.wait_for_timeout(random.randint(80, 180))
        await self.page.mouse.down()
        
        # 按照轨迹滑动
        for point in track:
            move_x = start_x + point["x"]
            move_y = start_y + point["y"]
            await self.page.mouse.move(move_x, move_y, steps=random.randint(2, 5))
            # 注意：这里的t是累计时间，我们需要计算每步的延迟
            if len(track) > 1:
                await self.page.wait_for_timeout(random.randint(10, 30))
        
        # 稍微等待
        await self.page.wait_for_timeout(200)
        
        # 释放鼠标
        await self.page.mouse.up()
        
        # 等待验证结果
        await self.page.wait_for_timeout(1500)
        
        return await self._check_slide_result()
    
    async def _check_slide_result(self) -> bool:
        """检查滑块验证结果"""
        try:
            # 检查验证码容器
            captcha_container = await self.page.query_selector("div.yidun_popup--light")
            
            if not captcha_container:
                # 容器不存在，验证成功
                logger.info("[验证结果] 验证码容器不存在")
                return True
            
            # 检查display样式
            display = await captcha_container.evaluate("el => window.getComputedStyle(el).display")
            
            if display == "none":
                # 容器被隐藏，验证成功
                logger.info("[验证结果] 验证码容器已隐藏 (display: none)")
                return True
            else:
                # 容器还在显示，验证未完成或失败
                logger.info(f"[验证结果] 验证码容器仍显示 (display: {display})")
                return False
        except Exception as e:
            logger.warning(f"[验证结果] 检查出错: {e}")
            return False
    
    async def solve(self) -> bool:
        """
        解决滑块验证码
        返回: 是否成功
        """
        logger.info("=" * 50)
        logger.info("开始处理滑块验证码")
        logger.info("=" * 50)
        distance_offsets = [0, -4, 4, -8, 8]
        
        for attempt in range(self.config.SLIDER_RETRY_COUNT):
            logger.info(f"第 {attempt + 1}/{self.config.SLIDER_RETRY_COUNT} 次尝试")
            
            try:
                # 获取验证码图片
                bg_bytes, slider_bytes = await self.get_captcha_images()
                logger.info(f"背景图大小: {len(bg_bytes)} bytes, 滑块图大小: {len(slider_bytes)} bytes")
                await self.save_page_debug(f"captcha_page_before_attempt_{attempt + 1}")
                
                # 计算滑动距离
                slide_info = await self.calculate_slide_distance(bg_bytes, slider_bytes)
                base_distance = slide_info["distance"]
                retry_offset = distance_offsets[min(attempt, len(distance_offsets) - 1)]
                total_offset = self.config.SLIDER_BASE_OFFSET + retry_offset
                distance = max(0, round(base_distance + total_offset))
                logger.info(
                    f"滑动距离: {distance}px (基础距离: {base_distance:.2f}px, 基础补偿: {self.config.SLIDER_BASE_OFFSET}px, "
                    f"重试补偿: {retry_offset}px, 总补偿: {total_offset}px), "
                    f"缺口位置: ({slide_info['target_x']}, {slide_info['target_y']})"
                )
                
                # 生成滑动轨迹
                track = self.get_slide_track(distance)
                logger.info(f"生成轨迹点数: {len(track)}")
                
                # 执行滑动
                success = await self.perform_slide(track)
                
                if success:
                    logger.info("✓ 验证成功!")
                    return True
                else:
                    logger.info("✗ 验证失败，准备重试...")
                    await self.save_page_debug(f"captcha_page_after_attempt_{attempt + 1}")
                    await self.page.wait_for_timeout(1500)
                    
            except Exception as e:
                logger.error(f"✗ 出错: {e}，准备重试...")
                await self.save_page_debug(f"captcha_page_error_attempt_{attempt + 1}")
                await self.page.wait_for_timeout(1500)
        
        logger.error("=" * 50)
        logger.error(f"超过最大重试次数 ({self.config.SLIDER_RETRY_COUNT})，验证失败")
        logger.error("=" * 50)
        return False
