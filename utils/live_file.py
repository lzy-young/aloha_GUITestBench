

import abc
import os.path

from utils.fileio import load, save

class LiveFile(abc.ABC):
    def __init__(self, filepath: str):
        self._filepath = filepath
        self._data = load(self._filepath)
        self._last_version = os.path.getmtime(self._filepath)

    def _ensure_newest(self):
        if os.path.getmtime(self._filepath) != self._last_version:
            self._data = load(self._filepath)
            self._last_version = os.path.getmtime(self._filepath)



class LiveJsonFile(LiveFile):
    def __init__(self, filepath: str):
        super().__init__(filepath)

    def __iter__(self):
        return iter(self._data)

    def __contains__(self, item):
        return item in self._data

    def __getitem__(self, key: str):
        self._ensure_newest()
        return self._data[key]

    def __setitem__(self, key: str, value):
        self._data[key] = value
        save(self._filepath, self._data)
        self._last_version = os.path.getmtime(self._filepath)


class LiveTextFile(LiveFile):
    def __init__(self, filepath: str):
        super().__init__(filepath)

    def __str__(self):
        self._ensure_newest()
        return str(self._data)

    def __get__(self, instance, owner):
        self._ensure_newest()
        return self._data

    def __set__(self, instance, value):
        save(self._filepath, value)
        self._data = value
