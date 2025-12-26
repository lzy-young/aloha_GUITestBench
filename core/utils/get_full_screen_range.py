from pyautogui import size


def get_full_screen_range() -> tuple[tuple[int, int], tuple[int, int]]:
    w, h = size()
    return (0, 0), (w, h)
