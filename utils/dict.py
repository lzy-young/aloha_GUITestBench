from typing import Any


def get_dict_value(d: dict, key: str, fallback_val: Any = None, except_val: list = None) -> Any:
    if except_val is None:
        except_val = []
    if key not in d:
        return fallback_val
    for v in except_val:
        if v == d[key]:
            return fallback_val
    return d[key]
