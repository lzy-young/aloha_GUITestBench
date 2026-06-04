from typing import Union, Literal

from PIL import Image, ImageDraw, ImageFont


def create_label(img_size: tuple[int, int],
                 grid_size: int,
                 margin: tuple[int, int, int, int],
                 label_offset: int,
                 ) -> list[tuple[int, int, str, str]]:
    
    res: list[tuple[int, int, str, str]] = []
    
    if margin[0] != 0:
        for i in range(grid_size, img_size[0], grid_size):
            res.append((i + margin[3], margin[0] - label_offset, str(i), 'mb'))
        res.append((margin[3], margin[0] - label_offset, str(0), 'lb'))
        res.append((img_size[0] + margin[3], margin[0] - label_offset, str(img_size[0]), 'rb'))
    
    if margin[1] != 0:
        for i in range(grid_size, img_size[1], grid_size):
            res.append((margin[3] + img_size[0] + label_offset, i + margin[0], str(i), 'lm'))
        res.append((margin[3] + img_size[0] + label_offset, margin[0], str(0), 'lt'))
        res.append((margin[3] + img_size[0] + label_offset, img_size[1] + margin[0], str(img_size[1]), 'lb'))
    
    if margin[2] != 0:
        for i in range(grid_size, img_size[0], grid_size):
            res.append((i + margin[3], margin[0] + img_size[1] + label_offset, str(i), 'mt'))
        res.append((margin[3], margin[0] + img_size[1] + label_offset, str(0), 'lt'))
        res.append((img_size[0] + margin[3], margin[0] + img_size[1] + label_offset, str(img_size[0]), 'rt'))
    
    if margin[3] != 0:
        for i in range(grid_size, img_size[1], grid_size):
            res.append((margin[3] - label_offset, i + margin[0], str(i), 'rm'))
        res.append((margin[3] - label_offset, margin[0], str(0), 'rt'))
        res.append((margin[3] - label_offset, img_size[1] + margin[0], str(img_size[1]), 'rb'))
    return res


def create_axis_line(img_size: tuple[int, int],
                     grid_size: int,
                     margin: tuple[int, int, int, int],
                     indicator_size: int) \
        -> list[tuple[int, int, int, int, Literal['axis', 'grid']]]:
    
    res: list[tuple[int, int, int, int, Literal['axis', 'grid']]] = []
    
    for i in [*range(0, img_size[0], grid_size), img_size[0]]:
        res.append((i + margin[3], margin[0],
                    i + margin[3], margin[0] + img_size[1],
                    'grid'))
    
    for i in [*range(0, img_size[1], grid_size), img_size[1]]:
        res.append((margin[3], i + margin[0],
                    margin[3] + img_size[0], i + margin[0],
                    'grid'))
    
    if margin[0] != 0:
        res.append((margin[3], margin[0],
                    margin[3] + img_size[0], margin[0],
                    'axis'))
        for i in [*range(0, img_size[0], grid_size), img_size[0]]:
            res.append((i + margin[3], margin[0],
                        i + margin[3], margin[0] + indicator_size,
                        'axis'))
    
    if margin[1] != 0:
        res.append((margin[3] + img_size[0], margin[0],
                    margin[3] + img_size[0], margin[0] + img_size[1],
                    'axis'))
        for i in [*range(0, img_size[1], grid_size), img_size[1]]:
            res.append((margin[3] + img_size[0] - indicator_size, i + margin[0],
                        margin[3] + img_size[0], i + margin[0],
                        'axis'))
    
    if margin[2] != 0:
        res.append((margin[3], margin[0] + img_size[1],
                    margin[3] + img_size[0], margin[0] + img_size[1],
                    'axis'))
        for i in [*range(0, img_size[0], grid_size), img_size[0]]:
            res.append((i + margin[3], margin[0] + img_size[1],
                        i + margin[3], margin[0] + img_size[1] - indicator_size,
                        'axis'))
    
    if margin[3] != 0:
        res.append((margin[3], margin[0],
                    margin[3], margin[0] + img_size[1],
                    'axis'))
        for i in [*range(0, img_size[1], grid_size), img_size[1]]:
            res.append((margin[3], i + margin[0],
                        margin[3] + indicator_size, i + margin[0],
                        'axis'))
    return res


def add_coordinate(img: Image.Image,
                   grid_size: int = 100,
                   margin: tuple[int, int, int, int] = (0, 60, 30, 0),  # top, right, bottom, left
                   background_color: Union[tuple[int, int, int], tuple[int, int, int, int]] = (255, 255, 255, 255),
                   axis_line_color: Union[tuple[int, int, int], tuple[int, int, int, int]] = (0, 0, 0),
                   axis_line_width: int = 3,
                   grid_line_color: Union[tuple[int, int, int], tuple[int, int, int, int]] = (0, 0, 0, 70),
                   grid_line_width: int = 1,
                   axis_label_color: Union[tuple[int, int, int], tuple[int, int, int, int]] = (0, 0, 0),
                   axis_label_font_size: int = 14,
                   label_offset: int = 10,
                   indicator_size: int = 7,
                   ) -> Image.Image:
   
    orig_width, orig_height = img.size
    new_width = orig_width + margin[1] + margin[3]
    new_height = orig_height + margin[0] + margin[2]
    img_with_grid = Image.new('RGBA', (new_width, new_height), background_color).convert("RGBA")
    img_with_grid.paste(img, (margin[3], margin[0]))
    
    line_styles = {
        "axis": {
            "fill": axis_line_color,
            "width": axis_line_width,
        },
        "grid": {
            "fill": grid_line_color,
            "width": grid_line_width,
        },
    }
    img_overlay = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(img_overlay)
    for x1, y1, x2, y2, style in create_axis_line(img.size, grid_size, margin, indicator_size):
        overlay_draw.line([(x1, y1), (x2, y2)], fill=line_styles[style]['fill'], width=line_styles[style]['width'])
    img_with_grid = Image.alpha_composite(img_with_grid, img_overlay)
    
    try:
        font = ImageFont.truetype("arial.ttf", axis_label_font_size)
    except:
        try:
            font = ImageFont.load_default(axis_label_font_size)
        except:
            font = None
    # endregion
    img_overlay = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(img_overlay)
    for x, y, t, anchor in create_label(img.size, grid_size, margin, label_offset):
        overlay_draw.text((x, y), t, fill=axis_label_color, font=font, anchor=anchor)
    img_with_grid = Image.alpha_composite(img_with_grid, img_overlay)
    # endregion

    return img_with_grid
