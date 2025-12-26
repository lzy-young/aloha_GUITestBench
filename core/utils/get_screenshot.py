import base64
import os.path
from pathlib import Path
from typing import Union

import pyautogui
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from utils.img import encoding2url


def add_none(img: Image.Image, text: str) -> None:
    return

def add_text(img: Image.Image, text: str) -> None:
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default().font_variant(size=60)
    
    img_width, img_height = img.size
    
    
    center_x = img_width // 2
    center_y = img_height // 2
    bg_color = img.getpixel((center_x, center_y))
    
    
    if isinstance(bg_color, tuple) and len(bg_color) == 4:
        bg_color = bg_color[:3]
    
    
    brightness = (0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2])
    
    
    text_color = (255, 255, 255) if brightness < 128 else (0, 0, 0)
    
    
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    
    x = (img_width - text_width) // 2
    y = (img_height - text_height) // 2
    
    
    draw.text((x, y), text, font=font, fill=text_color)

def add_cursor(img: Image.Image, cx: int, cy: int) -> None:
    cursor_img = Image.open(os.path.join(Path(__file__).parent, 'cursor.png'))
    cursor_img = cursor_img.resize((48, 72))
    img.paste(cursor_img, (cx, cy), mask=cursor_img)

def cursor_swipe(img: Image.Image, start_point: tuple[int, int], end_point: tuple[int, int]) -> None:
    cursor_img = Image.open(os.path.join(Path(__file__).parent, 'cursor.png'))
    cursor_img = cursor_img.resize((48, 72))
    
    draw = ImageDraw.Draw(img)
    draw.line([start_point, end_point], fill=(255, 0, 0), width=10)
    
    
    num_steps = 10
    for i in range(num_steps + 1):
        t = i / num_steps
        x = int(start_point[0] + (end_point[0] - start_point[0]) * t)
        y = int(start_point[1] + (end_point[1] - start_point[1]) * t)
        
        alpha = int(50 + 205 * t)  
        cursor_copy = cursor_img.copy()
        cursor_copy.putalpha(alpha)
        
        img.paste(cursor_copy, (x, y), cursor_copy)
    
    draw.ellipse([start_point[0]-5, start_point[1]-5, 
                  start_point[0]+5, start_point[1]+5], 
                 fill=(0, 255, 0), outline=(0, 200, 0))
    
    draw.ellipse([end_point[0]-5, end_point[1]-5, 
                  end_point[0]+5, end_point[1]+5], 
                 fill=(255, 0, 0), outline=(200, 0, 0))

def add_hand(img: Image.Image, cx: int, cy: int) -> None:
    cursor_img = Image.open(os.path.join(Path(__file__).parent, 'cursor-hand-click.png')).convert("RGBA")
    cursor_img = cursor_img.resize((54, 72))
    img.paste(cursor_img, (cx, cy), mask=cursor_img)

def screenshot_post_process(img: Image.Image, cursor: tuple[int, int] = None) -> str:
    if cursor is not None:  
        add_cursor(img, cursor[0], cursor[1])
    buffer = BytesIO()
    img.save(buffer, format="png")
    img_str = base64.b64encode(buffer.getvalue()).decode('utf8')
    return encoding2url(img_str)

def screenshot_post_process_v2(img: Union[Image.Image, str], cursor: tuple[int, int] = None) -> str:
    print(f"这里处理图片screenshot_post_process_v2: {img}")
    if isinstance(img, str):
        if os.path.exists(img):
            img = Image.open(img)
        else:
            raise FileNotFoundError(f"图像文件路径不存在: {img}")
    elif not isinstance(img, Image.Image):
        raise TypeError(f"img参数类型必须是Image对象或字符串路径，当前类型: {type(img)}")
    
    if cursor is not None:
        add_cursor(img, cursor[0], cursor[1])

    buffer = BytesIO()
    img.save(buffer, format="png")
    img_str = base64.b64encode(buffer.getvalue()).decode('utf8')
    return encoding2url(img_str)

def get_screenshot(screen_range: tuple[tuple[int, int], tuple[int, int]],
                   with_cursor:bool=True) -> str:
    x = screen_range[0][0]
    y = screen_range[0][1]
    w = screen_range[1][0] - screen_range[0][0]
    h = screen_range[1][1] - screen_range[0][1]

    img = pyautogui.screenshot(region=(x, y, w, h))

    if with_cursor:
        cx, cy = pyautogui.position()
        cx -= x
        cy -= y
        if cx <= w and cy <= h:
            cursor = (cx, cy)
        else:
            cursor = None
    else:
        cursor = None
    return screenshot_post_process(img, cursor=cursor)
