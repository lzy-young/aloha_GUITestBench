import re
from typing import List, Union

from .types import Action, ClickAction, DoubleClickAction, RightClickAction, DragAction, MoveAction, PressAction, \
    HotkeyAction, TypeAction, ScrollAction, WaitAction, FinishedAction

black_list=[
    'x1=',
    'x2=',
    'x3=',
    'x4=',
    'y1=',
    'y2=',
    'y3=',
    'y4=',
]


def clean_action(action_str: str) -> str:
    for s in black_list:
        action_str = action_str.replace(s, '')
    return action_str.strip()


def parse_click_action(action_str: str) -> ClickAction:
    x, y = re.findall(r"\d+", action_str)
    return ClickAction(pos=(int(x.strip()), int(y.strip())))


def parse_left_double_action(action_str: str) -> DoubleClickAction:
    x, y = re.findall(r"\d+", action_str)
    return DoubleClickAction(pos=(int(x.strip()), int(y.strip())))


def parse_right_single_action(action_str: str) -> RightClickAction:
    x, y = re.findall(r"\d+", action_str)
    return RightClickAction(pos=(int(x.strip()), int(y.strip())))


def parse_drag_action(action_str: str) -> DragAction:
    x1, y1, x2, y2 = re.findall(r"\d+", action_str)
    return DragAction(start_pos=(int(x1.strip()), int(y1.strip())), end_pos=(int(x2.strip()), int(y2.strip())))


def parse_hover_action(action_str: str) -> MoveAction:
    x, y = re.findall(r"\d+", action_str)
    return MoveAction(pos=(int(x.strip()), int(y.strip())))


def parse_long_press_action(action_str: str) -> PressAction:
    x, y, t = re.findall(r"\d+(\.\d+)?", action_str)
    return PressAction(pos=(int(x.strip()), int(y.strip())), milliseconds=int(float(t.strip()) * 1000))


def parse_hotkey_action(action_str: str) -> HotkeyAction:
    key = action_str[7:-1]
    if key.startswith("key="):
        key = key[4:]
    if key.startswith('"') or key.startswith("'"):
        key = key[1:-1]
    return HotkeyAction(hotkey=key)


def parse_type_action(action_str: str) -> TypeAction:
    content = action_str[5:-1]
    if content.startswith('content='):
        content = content[8:]
    if content.startswith('"') or content.startswith("'"):
        content = content[1:-1]
    return TypeAction(content=content)


def parse_scroll_action(action_str: str) -> ScrollAction:
    direction = action_str[7:-1]
    if direction.startswith('"') or direction.startswith("'"):
        direction = direction[1:-1]
    if direction not in ['down', 'up', 'right', 'left']:
        direction = 'down'
    return ScrollAction(direction=direction)


def parse_wait_action(action_str: str) -> WaitAction:
    time = action_str[5:-1]
    if time == '':
        time = '5'
    return WaitAction(milliseconds=int(float(time.strip()) * 1000))


def parse_finished_action(action_str: str) -> FinishedAction:
    params = action_str[9:-1]
    if len(params) == 0:
        return FinishedAction(success=True, reason="Finish")
    success, reason = action_str[9:-1].split(',')
    if reason.startswith('"'):
        reason = reason.strip()[1:-1]
    return FinishedAction(success=success.strip() == 'True', reason=reason.strip())



action_space = {
    'click': parse_click_action,
    'left_double': parse_left_double_action,
    'right_single': parse_right_single_action,
    'drag': parse_drag_action,
    'hover': parse_hover_action,
    'long_press': parse_long_press_action,
    'hotkey': parse_hotkey_action,
    'type': parse_type_action,
    'scroll': parse_scroll_action,
    'wait': parse_wait_action,
    'finished': parse_finished_action,
}

def parse_action(action_str: str) -> Union[Action, None]:
    try:
        action_str = clean_action(action_str)

        for key in action_space:
            if action_str.startswith(key):
                return action_space[key](action_str)
        return None
    except Exception:
        return None


def parse_actions(actions_str: str) -> list[Action]:
    actions_str = actions_str.split('\n')
    actions = []
    for action_str in actions_str:
        action_str = action_str.strip()
        if action_str == '':
            continue
        action = parse_action(action_str)
        if action is None:
            print('Unrecognized Action: ', action_str)
            continue
        actions.append(action)
    return actions
