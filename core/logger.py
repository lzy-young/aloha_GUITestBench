import os
import time
from typing import Any, Optional

from pathvalidate import sanitize_filepath
from pydantic.v1 import PathNotAFileError

from utils.fileio import save


class MyLogger:
    _log_dir: str
    __index: list[int]
    _log_files: dict

    def __init__(self, log_dir = None) -> None:
        if log_dir is None:
            log_dir = ('./logs', 'log')
            log_dir = os.path.join(log_dir[0], time.strftime("%Y%m%d-%H%M", time.localtime()) + f'-{log_dir[1]}')
            cnt = 0
            while os.path.isdir(f"{log_dir}-{str(cnt)}"):
                cnt += 1
            self.log_dir = f"{log_dir}-{str(cnt)}"
        elif isinstance(log_dir, tuple):
            log_dir = os.path.join(log_dir[0], time.strftime("%Y%m%d-%H%M", time.localtime()) + f'-{log_dir[1]}')
            cnt = 0
            while os.path.isdir(f"{log_dir}-{str(cnt)}"):
                cnt += 1
            self.log_dir = f"{log_dir}-{str(cnt)}"
        else:
            self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.logging_files = {}
        self.__index = [0, 0]

    def patch_log(self, index: list[int], name: str, content: str, close: bool = False) -> None:
        if not (name.endswith('.md') or name.endswith('.txt')):
            raise TypeError('Patch Log only supports .md and .txt file.')
        filepath = os.path.join(self.log_dir, f"{index[0]}.{index[1]}.{name}")
        if not os.path.isfile(filepath):
            raise PathNotAFileError(f'Filepath {filepath} does not exists.')

        if filepath not in self.logging_files:
            self.logging_files[filepath] = open(filepath, 'a', encoding='utf-8')
        f = self.logging_files[filepath]
        f.write(content)

        if close:
            f.close()
            del self.logging_files[filepath]

    def log(self, name: str, content: Any, index: Optional[list[int]] = None) -> list[int]:
        if index is None:
            self.__index[1] += 1
            index = [v for v in self.__index]
        name = name.replace(r'\\/', '__')
        save(os.path.join(self.log_dir, f"{index[0]}.{index[1]}.{name}"), content)
        return index

    def record(self, name: str, content: Any) -> None:
        name = name.replace(r'\\/', '__')
        print(content)
        print("-"*175+'\n')
        save(os.path.join(self.log_dir, f"{name}"), content)

    def log_files(self, folder_name: str, codes: list[tuple[str, Any]]) -> list[int]:
        self.__index[1] += 1
        index = [*self.__index]
        folder = os.path.join(self.log_dir, f"{index[0]}.{index[1]}.{folder_name}")
        folder = sanitize_filepath(folder)
        os.mkdir(folder)
        for code in codes:
            save(os.path.join(folder, code[0]), code[1])
        return index

    def new_log_cycle(self) -> None:
        self.__index[0] += 1
        self.__index[1] = 0
