import base64
import math
from io import BytesIO
from typing import Literal, Optional, Union

import cv2
import numpy as np
from PIL import Image
from PIL.ImageDraw import Draw


def encoding2url(encoding: str, mime_type: str = 'image/png') -> str:
    return f"data:{mime_type};base64,{encoding}"


def url2encoding(url: str) -> str:
    return url.split(',', maxsplit=1)[1]


def url2img(url: str) -> Image.Image:
    encoding = url2encoding(url)
    return Image.open(BytesIO(base64.b64decode(encoding)))


def img2url(img: Image.Image) -> str:
    bytes_io = BytesIO()
    img.save(bytes_io, format='png')
    encoding = base64.b64encode(bytes_io.getvalue()).decode("utf-8")
    return encoding2url(encoding)


def url2cv2(url: str) -> cv2.typing.MatLike:
    return cv2.cvtColor(np.array(url2img(url)), cv2.COLOR_RGBA2BGRA)


def cv22url(img: cv2.typing.MatLike) -> str:
    return img2url(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)))


def crop_img_cv2(img: cv2.typing.MatLike, bbox: tuple[float, float, float, float]) -> cv2.typing.MatLike:
    x1, y1, x2, y2 = map(int, bbox)
    return img[y1:y2, x1:x2].copy()


def replace_img_cv2(img: cv2.typing.MatLike, bbox: tuple[float, float, float, float], tgt: cv2.typing.MatLike) -> None:
    x1, y1, x2, y2 = map(int, bbox)
    x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, img.shape[1] - 1), min(y2, img.shape[0] - 1)
    w, h = x2 + 1 - x1, y2 + 1 - y1
    if w <= 0 or h <= 0:
        return
    resized_tgt = cv2.resize(tgt, (w, h), interpolation=cv2.INTER_LANCZOS4)

    img[y1:y2 + 1, x1:x2 + 1] = resized_tgt


def resize_img(img_url: str, target_size: tuple[int, int]) -> str:
    img = url2img(img_url)
    img = img.resize(target_size, Image.LANCZOS)
    return img2url(img)


def compress_img(img_url: str, resolution_limit: int = 1150000, max_wh_limit: int = 1568) -> tuple[str, float]:
    
    header, _ = img_url.split(",", 1)
    mime_type = header.split(";")[0].split(":")[1]


    img = url2img(img_url)

    
    width, height = img.size
    current_pixels = width * height

    if max(width, height) <= max_wh_limit and current_pixels <= resolution_limit:
        return img_url, 1  

    
    scale = min(
        math.sqrt(resolution_limit / current_pixels),
        max_wh_limit / width,
        max_wh_limit / height,
    )
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))

   
    img = img.resize((new_width, new_height), Image.LANCZOS)


    img_format = mime_type.split("/")[-1].upper()
    if img_format == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")

    
    return img2url(img), scale


def concat_img(
        images_url: list[str],
        layout: Literal['vertical', 'horizontal', 'auto_min_area', 'auto_min_circumference'] = 'auto_min_circumference',
        divider_color: tuple[int, int, int] = (0, 0, 0),
        divider_width: int = 5,
) -> tuple[str, Literal['vertical', 'horizontal']]:
    images = [url2img(url) for url in images_url]
    widths, heights = zip(*(i.size for i in images))

    if layout == 'auto_min_area':
        divider_len = (len(images) - 1) * divider_width
        h_area = (sum(widths) + divider_len) * max(heights)
        v_area = (sum(heights) + divider_len) * max(widths)
        layout = 'horizontal' if h_area < v_area else 'vertical'
    elif layout == 'auto_min_circumference':
        h_c = sum(widths) + max(heights)
        v_c = sum(heights) + max(widths)
        layout = 'horizontal' if h_c < v_c else 'vertical'

    total_width = sum(widths) if layout == 'horizontal' else max(widths)
    total_height = sum(heights) if layout == 'vertical' else max(heights)

    merged_image = Image.new('RGB', (total_width, total_height))
    merged_image.paste(divider_color, (0, 0, total_width, total_height))
    offset = 0
    for image in images:
        merged_image.paste(image, (offset, 0) if layout == 'horizontal' else (0, offset))
        offset += image.size[0] if layout == 'horizontal' else image.size[1]

        offset += divider_width

    return img2url(merged_image), layout


def cut_image_pil(img: Image, pos: tuple[int, int], size: tuple[int, int]) -> Optional[Image.Image]:
    x1, y1 = pos
    x2, y2 = pos[0] + size[0], pos[1] + size[1]
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    x1 = max(0, min(img.size[0], x1))
    x2 = max(0, min(img.size[0], x2))
    y1 = max(0, min(img.size[1], y1))
    y2 = max(0, min(img.size[1], y2))
    if x1 == x2 or y1 == y2:
        return None
    return img.crop((x1, y1, x2, y2))


def cut_image(img_url: Union[str, Image.Image], pos: tuple[int, int], size: tuple[int, int]) -> Optional[str]:
    if isinstance(img_url, str):
        img = url2img(img_url)
    else:
        img = img_url
    node_img = cut_image_pil(img, pos, size)
    if node_img is None:
        return None
    return img2url(node_img)


def add_boxes_in_image(img_url: str,
                       boxes: list[tuple[tuple[int, int], tuple[int, int]]],
                       with_index: bool = False) -> str:
    img = url2img(img_url)
    draw = Draw(img)
    for box_id, box in enumerate(boxes):
        draw.rectangle((box[0], (box[0][0] + box[1][0], box[0][1] + box[1][1])), fill=None, outline='red')
        if with_index:
            draw.text((box[0][0] + box[1][0] // 2, box[0][1] + box[1][1] // 2), f'{box_id}', fill=(255, 0, 0))
    return img2url(img)


def pad_image(img_url: str, tile_size: int,
              tile_limits_total: int = 15000,
              tile_limits_h: int = -1,
              tile_limits_v: int = -1) -> tuple[str, tuple[int, int], float]:
    img = url2img(img_url)
    h_tile_num = math.ceil(img.size[0] / tile_size)
    v_tile_num = math.ceil(img.size[1] / tile_size)
    while ((tile_limits_total != -1 and h_tile_num * v_tile_num > tile_limits_total)
           or (tile_limits_h != -1 and h_tile_num > tile_limits_h)
           or (tile_limits_v != -1 and v_tile_num > tile_limits_v)):
        if h_tile_num > 1 and img.size[1] / img.size[0] > (v_tile_num - 1) / (h_tile_num - 1):
            h_tile_num -= 1
        elif v_tile_num > 1:
            v_tile_num -= 1

    scale = min(1, h_tile_num * tile_size / img.size[0], v_tile_num * tile_size / img.size[1])
    resized_img = img.resize((int(scale * img.size[0]), int(scale * img.size[1])), Image.Resampling.LANCZOS)

    new_img = Image.new('RGB', (h_tile_num * tile_size, v_tile_num * tile_size), (1, 1, 1))
    new_img.paste(resized_img, (0, 0))

    return img2url(new_img), (h_tile_num, v_tile_num), scale


def add_bg_color(img_url: str, color: tuple[int, int, int]) -> str:
    ori_img = url2img(img_url).convert("RGBA")
    new_img = Image.new('RGBA', ori_img.size, (color[0], color[1], color[2], 255))
    new_img.paste(ori_img, (0, 0), ori_img)
    return img2url(new_img)
