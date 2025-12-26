import time
from time import sleep

import pyperclip
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController

from core.utils import get_full_screen_range
from core.utils.types import Action, Pos, DragAction, MoveAction, PressAction, \
    HotkeyAction, TypeAction, ScrollAction, WaitAction

mouse = MouseController()
keyboard = KeyboardController()


def transfer_pos(pos: Pos, screen_range: tuple[Pos, Pos]) -> Pos:
    w = screen_range[1][0] - screen_range[0][0]
    h = screen_range[1][1] - screen_range[0][1]
    return pos[0] * w // 1000 + screen_range[0][0], pos[1] * h // 1000 + screen_range[0][1]


def move_to(pos: Pos, speed: float = 2000, dragging: bool = False) -> None:
    cx, cy = mouse.position
    tx, ty = pos
    dis = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
    duration = dis / speed
    if dragging:
        mouse.press(Button.left)

    t = 0
    interval = 0.02
    while t < duration:
        t += interval
        rate = min(t, duration) / duration
        tgt_pos = (tx * rate + cx * (1 - rate), ty * rate + cy * (1 - rate))
        mouse.move(tgt_pos[0] - mouse.position[0], tgt_pos[1] - mouse.position[1])
        sleep(interval * 2)

    if dragging:
        mouse.release(Button.left)


def perform_click(pos: Pos, screen_range: tuple[Pos, Pos], button: Button = Button.left, count: int = 1) -> float:
    move_to(transfer_pos(pos, screen_range))
    t1 = time.time()
    mouse.click(button, count=count)
    t2 = time.time()
    return (t1 + t2) / 2


def perform_drag(action: DragAction, screen_range: tuple[Pos, Pos]) -> None:
    start_pos = transfer_pos(action.start_pos, screen_range)
    end_pos = transfer_pos(action.end_pos, screen_range)
    move_to(start_pos)
    move_to(end_pos, dragging=True)


def perform_hover(action: MoveAction, screen_range: tuple[Pos, Pos]) -> None:
    pos = transfer_pos(action.pos, screen_range)
    move_to(pos)


def perform_long_press(action: PressAction, screen_range: tuple[Pos, Pos]) -> None:
    pos = transfer_pos(action.pos, screen_range)
    move_to(pos)
    mouse.press(Button.left)
    sleep(action.milliseconds / 1000.0)
    mouse.release(Button.left)


def perform_hotkey(action: HotkeyAction) -> None:
    keys = action.hotkey.lower()
    # with keyboard
    keys = [key.strip() for key in keys.split('+')]

    def press_key(idx: int) -> None:
        if idx == len(keys):
            return
        with keyboard.pressed(keys[idx]):
            press_key(idx + 1)

    press_key(0)


def perform_type(action: TypeAction) -> None:
    pyperclip.copy(action.content)
    with keyboard.pressed(Key.ctrl):
        keyboard.press('v')
        keyboard.release('v')


def perform_scroll(action: ScrollAction) -> None:
    amount = 10
    if action.direction == 'left':
        # ! seems to work only on Unix system
        mouse.scroll(-amount, 0)
    elif action.direction == 'right':
        # ! seems to work only on Unix system
        mouse.scroll(amount, 0)
    elif action.direction == 'up':
        mouse.scroll(0, -amount)
    else:
        # default as down
        mouse.scroll(0, amount)


def perform_wait(action: WaitAction) -> None:
    sleep(action.milliseconds / 1000.0)


action_space = {
    'click': lambda x, sr: perform_click(x.pos, sr),
    'double_click': lambda x, sr: perform_click(x.pos, sr, count=1),
    'right_click': lambda x, sr: perform_click(x.pos, sr, button=Button.right, count=1),
    'drag': perform_drag,
    'hover': perform_hover,
    'move': perform_hover,
    'long_press': perform_long_press,
    'hotkey': lambda x, _: perform_hotkey(x),
    'type': lambda x, _: perform_type(x),
    'scroll': lambda x, _: perform_scroll(x),
    'wait': lambda x, _: perform_wait(x),
}


def perform_action(action: Action, screen_range: tuple[Pos, Pos]) -> float:
    if action.type in action_space:
        res = action_space[action.type](action, screen_range)
        return res if res is not None else time.time()

    print('Unsupported action to perform: ', action)
    return time.time()


def perform_actions(actions: list[Action], screen_range: tuple[Pos, Pos]) -> bool:
    for action in actions:
        if perform_action(action, screen_range):
            return True
    return False


if __name__ == '__main__':
    move_to(transfer_pos((500, 3), get_full_screen_range()), dragging=False)
    move_to(transfer_pos((500, 500), get_full_screen_range()), dragging=True)
