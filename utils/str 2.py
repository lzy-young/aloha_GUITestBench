import re
import time


def iter_str(s: str, chunk_size: int = 10, wait: float = 0):
    for i in range(0, len(s), chunk_size):
        yield s[i:i + chunk_size]
        time.sleep(wait)


def to_camel_case(any_case: str):
    segments = re.split(r'[-_ ]', any_case)
    return ''.join([f'{seg[0].upper()}{seg[1:]}' for seg in segments])
