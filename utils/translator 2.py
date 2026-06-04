import os.path
import re
from typing import Any, Optional

from utils.fileio import load


class Translator:
    locale_folder: str
    lang: str
    ns: str
    dicts: dict[str, dict[str, str]]

    def __init__(self, lang: str, ns: str,
                 locale_folder: str = './locales') -> None:
        self.lang = lang
        self.ns = ns
        self.locale_folder = locale_folder
        self.dicts = {}
        self.load_dict()

    def set_locale_folder(self, locale_folder: str) -> None:
        self.locale_folder = locale_folder
        self.load_dict()

    def set_lang(self, lang: str) -> None:
        self.lang = lang
        self.load_dict()

    def set_namespace(self, ns: str) -> None:
        self.ns = ns
        self.load_dict(ns_only=True)

    def load_dict_file(self, lang: str, ns: str) -> None:
        dict_path = os.path.join(self.locale_folder, lang, f'{ns}.json')
        d = load(dict_path)
        if d is None:
            print(f'Failed to load i18n dictionary: {dict_path}')
            d = {}
        self.dicts[ns] = d

    def load_dict(self, ns_only: bool = False) -> None:
        if not ns_only:
            self.dicts = {}
            self.load_dict_file(self.lang, 'common')
        self.load_dict_file(self.lang, self.ns)

    @staticmethod
    def apply_vars(template: str, params: Optional[dict[str, Any]]) -> str:
        if params:
            for key in params:
                template = re.sub('{{' + key + '}}', str(params[key]), template)
        return template

    def t(self, key: str,
          params: Optional[dict[str, Any]] = None,
          ns: Optional[str] = None) -> str:
        try_ns = [self.ns, 'common']
        if ns is not None:
            try_ns.insert(0, ns)

        for ns in try_ns:
            if ns not in self.dicts:
                self.load_dict_file(self.lang, ns)
            if key in self.dicts[ns]:
                return Translator.apply_vars(self.dicts[ns][key], params)
        print(f'Failed to find Key({key}). Folder({self.locale_folder}), Lang({self.lang}), TRY_NS({try_ns}).')
        return key
