import ast
import json
from typing import Any, Dict, Tuple
from PIL import Image, ImageDraw


def plot_action_vis(action: Dict[str, Any] | str, screenshot_path: str, action_vis_path: str) -> None:
    """Draw a red circle at the action coordinate on the screenshot, preserving original resolution."""

    def _extract_coord_xy(action_obj: Dict[str, Any]) -> Tuple[int, int] | None:
        pos = action_obj.get("position")
        if pos is None:
            return None
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                return int(pos[0]), int(pos[1])
            except Exception:
                return None
        try:
            parsed = ast.literal_eval(str(pos))
            if isinstance(parsed, (list, tuple)) and len(parsed) == 2:
                return int(parsed[0]), int(parsed[1])
        except Exception:
            return None
        return None

    img = Image.open(screenshot_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        action_content: Dict[str, Any]
        if isinstance(action, str):
            action_content = json.loads(action)
        else:
            action_content = action.get("content", action)

        pos = _extract_coord_xy(action_content)
        if pos:
            x, y = pos
            radius = 40
            color = (255, 0, 0)
            draw.ellipse([(x - radius, y - radius), (x + radius, y + radius)], outline=color, width=8)
    except Exception:
        pass

    img.save(action_vis_path)
