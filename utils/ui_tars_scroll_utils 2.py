import re
import ast
from typing import Dict, Optional, Tuple, Union



_BOX_IN_PARENS = re.compile(r"\(([^)]+)\)")

def _parse_box_any(box: Union[str, Tuple[float, ...], list]) -> Tuple[float, ...]:
    
    if box is None:
        raise ValueError("Empty box")

    
    if isinstance(box, (list, tuple)):
        vals = tuple(float(v) for v in box)
        if len(vals) in (2, 4):
            return vals
        raise ValueError(f"Unsupported box length: {len(vals)}")

    s = str(box).strip()

    
    try:
        lit = ast.literal_eval(s)
        if isinstance(lit, (list, tuple)) and len(lit) in (2, 4):
            return tuple(float(v) for v in lit)
    except Exception:
        pass

    
    m = _BOX_IN_PARENS.search(s)
    inner = m.group(1) if m else s.strip().strip("()[]")
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    vals = tuple(float(p) for p in parts)
    if len(vals) not in (2, 4):
        raise ValueError(f"Unsupported box format: {box}")
    return vals

def _center(vals: Tuple[float, ...]) -> Tuple[float, float]:
    return (vals[0], vals[1]) if len(vals) == 2 else ((vals[0]+vals[2])/2.0, (vals[1]+vals[3])/2.0)

def _to_pixels(x: float, y: float, W: float, H: float) -> Tuple[int, int]:
    if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
        return int(round(x * W)), int(round(y * H))
    return int(round(x)), int(round(y))

def _dir_to_delta(direction: str, magnitude: int = 300) -> Tuple[int, int]:
    d = (direction or "").lower()
    if "down" in d:  return (0, +magnitude)
    if "up" in d:    return (0, -magnitude)
    if "right" in d: return (+magnitude, 0)
    if "left" in d:  return (-magnitude, 0)
    return (0, 0)

def ui_tars_scroll_to_browsergym(
    action_inputs: Dict,
    image_width: int,
    image_height: int,
    *,
    magnitude: int = 500,
    cap_delta: Optional[int] = 1200,
    click_before_scroll: bool = False
):
    start_box = action_inputs.get("start_box")
    end_box   = action_inputs.get("end_box")
    direction = action_inputs.get("direction", "")
    
    browsergym_actions = []

    
    if start_box and end_box:
        sxn, syn = _center(_parse_box_any(start_box))
        exn, eyn = _center(_parse_box_any(end_box))
        sx, sy = _to_pixels(sxn, syn, image_width, image_height)
        ex, ey = _to_pixels(exn, eyn, image_width, image_height)
        dx, dy = ex - sx, ey - sy
        if cap_delta is not None:
            dx = max(-cap_delta, min(cap_delta, dx))
            dy = max(-cap_delta, min(cap_delta, dy))
        if click_before_scroll:
            browsergym_actions.append(f"mouse_click({sx}, {sy}, 'left')")
        browsergym_actions.append(f"scroll_at({sx}, {sy}, {dx}, {dy})")

   
    if start_box and direction:
        cxn, cyn = _center(_parse_box_any(start_box))
        cx, cy = _to_pixels(cxn, cyn, image_width, image_height)
        dx, dy = _dir_to_delta(direction, magnitude=magnitude)
        if click_before_scroll:
            browsergym_actions.append(f"mouse_click({cx}, {cy}, 'left')")
        browsergym_actions.append(f"scroll_at({cx}, {cy}, {dx}, {dy})")

   
    if direction and not start_box:
        dx, dy = _dir_to_delta(direction, magnitude=magnitude)
        browsergym_actions.append(f"scroll({dx}, {dy})")

    return browsergym_actions