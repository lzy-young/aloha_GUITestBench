

import base64
import json
import mimetypes
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Optional

from PIL.Image import Image
from pathvalidate import sanitize_filepath

from utils.img import url2encoding, encoding2url, img2url


def get_data(tag: str, params: dict, for_context: dict) -> Optional[Any]:
    var_chain = tag.split('.')

    if var_chain[0].startswith('for['):
        context_key = var_chain[0][4:-1]
        if context_key not in for_context:
            return None
        var = for_context[context_key]
        if len(var_chain) == 1 or var_chain[1] != '__index__':
            var_chain.insert(1, '__self__')
    else:
        if var_chain[0] not in params:
            return None
        var = params[var_chain[0]]

    for dp in var_chain[1:]:
        if dp not in var:
            return None
        var = var[dp]
    return var


def replace_for_context_lines(filename: str, lines: list[str], params: dict, for_context: dict,
                              start_line: int, data_source: str, map_name: str) -> int:
    old_prompt = ''
    lines.pop(start_line)
    while start_line < len(lines):
        if lines[start_line].find(fr'<<<endfor:{data_source}:{map_name}>') != -1:
            lines.pop(start_line)
            break
        old_prompt += lines.pop(start_line) + '\n'
    old_prompt = old_prompt[:-1]

    data = get_data(data_source, params, for_context)
    if data is None:
        print(f'Warning: {filename} requires param: {data_source}')
    elif not isinstance(data, list):
        print(f'Warning: {filename} requires param {data_source} to be a list!')
    else:
        for j, item in enumerate(data):
            wrap = {"__self__": item, '__index__': j + 1}
            block = load_prompt(
                filename,
                old_prompt,
                params=params,
                for_context={
                    **for_context,
                    map_name: wrap
                }
            )
            block_lines = block.split('\n')
            for bl in block_lines:
                lines.insert(start_line, bl)
                start_line += 1
    return start_line


def replace_for_context(filename: str, content: str, params: dict, for_context: dict) -> str:
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        res = re.findall(r'<<<for:([^>]*):([^>]*)>>>', lines[i])
        for data_source, map_name in res:
            i = replace_for_context_lines(filename, lines, params, for_context, i, data_source, map_name)
        i += 1
    return '\n'.join(lines)


def replace_file(filename: str, content: str) -> str:
    embedded_files = re.findall(r'<<<file:([^>]*)>>>', content)
    for file in embedded_files:
        if not os.path.isfile(file):
            print(f'Warning: {filename} requires file: {file}')
        else:
            content = content.replace(f'<<<file:{file}>>>', str(load(file)))
    return content


def replace_code(filename: str, content: str, params: dict, for_context: dict) -> str:
    embedded_code = re.findall(r'<<<code:([^>]*)>>>', content)
    for code in embedded_code:
        if os.path.isfile(code):
            content = content.replace(f'<<<code:{code}>>>',
                                      '\n'.join([
                                          f'l({i + 1}):\t{line}'
                                          for i, line in enumerate(load(code).split('\n'))
                                      ]))
        else:
            data = get_data(code, params, for_context)
            if data is None:
                print(f'Warning: {filename} requires code: {code}')
            else:
                content = content.replace(f'<<<code:{code}>>>',
                                          '\n'.join([
                                              f'l({i + 1}):\t{line}'
                                              for i, line in enumerate(data.split('\n'))
                                          ]))
    return content


def replace_params(filename: str, content: str, params: dict, for_context: dict) -> str:
    embedded_params = re.findall(r'<<<var:([^>]*)>>>', content)
    for param in embedded_params:
        data = get_data(param, params, for_context)
        if data is None:
            print(f'Warning: {filename} requires param: {param}')
        else:
            content = content.replace(f'<<<var:{param}>>>', str(data))
    return content


def load_prompt(filename: str, content: str, params: Optional[dict] = None, for_context: Optional[dict] = None) -> str:
    for_context = for_context or {}
    params = params or {}

    content = replace_for_context(filename, content, params, for_context)
    content = replace_file(filename, content)
    content = replace_code(filename, content, params, for_context)
    content = replace_params(filename, content, params, for_context)

    return content


def load(file_path: Any, params: Optional[dict] = None) -> Optional[Any]:
    if params is None:
        params = {}
    file_path = sanitize_filepath(file_path)
    if not os.path.isfile(file_path):
        return None
    filename = os.path.basename(file_path)
    if filename.endswith('.docx'):
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
            file_encodings = base64.b64encode(file_bytes).decode('utf8')
            return file_encodings
    
    if filename.endswith('.md') and filename.startswith('prompt'):
        with open(file_path, "r", encoding='utf8') as f:
            content = f.read()
            return load_prompt(filename, content, params)
    elif filename.endswith(".json"):
        with open(file_path, "r", encoding='utf8') as f:
            return json.load(f)
    elif filename.endswith(".png") or filename.endswith(".jpg"):
        with open(file_path, "rb") as f:
            mime_type = mimetypes.guess_type(file_path)[0]
            encoding = base64.b64encode(f.read()).decode('utf8')
            return encoding2url(encoding, mime_type)
    else:
        with open(file_path, "r", encoding='utf8') as f:
            return f.read()


def save(file_path: str, content: Any) -> None:
    file_path = sanitize_filepath(file_path)
    folder = os.path.dirname(file_path)
    if folder != '' and not os.path.isdir(os.path.dirname(file_path)):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

    if file_path.endswith(".json"):
        with open(file_path, "w+", encoding='utf8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
    elif file_path.endswith('.png') or file_path.endswith('.jpg'):
        with open(file_path, 'wb') as f:
            if isinstance(content, Image):
                content = img2url(content)
            encoding = url2encoding(content)
            decoded_bytes = base64.b64decode(encoding.encode('utf8'))
            f.write(decoded_bytes)
    elif file_path.endswith('.zip'):
        with open(file_path, 'wb+') as f:
            f.write(content)
    elif file_path.endswith('.log'):
        if not content.endswith('\n'):
            content += '\n\n'
        with open(file_path, "a+", encoding='utf8') as f:
            f.write(content)
    else:
        with open(file_path, "w+", encoding='utf8') as f:
            f.write(content)


def iter_files_in_folder(root_folder: str, cur_folder: str = '') -> list[str]:
    folder = os.path.join(root_folder, cur_folder)
    files = []
    for f in os.listdir(folder):
        if os.path.isdir(os.path.join(folder, f)):
            files.extend(iter_files_in_folder(root_folder, os.path.join(cur_folder, f)))
        else:
            files.append(os.path.join(cur_folder, f))
    return files


def backup_to_zip(folder: str, archive_folder: str = None) -> None:
    folder = os.path.abspath(folder)  
    if archive_folder is None:
        archive_folder = Path(folder).parent

    backup_index = 1
    while True:
        zip_filename = os.path.basename(folder) + '_' + str(backup_index) + '.zip'
        if not os.path.exists(os.path.join(archive_folder, zip_filename)):
            break
        backup_index = backup_index + 1

    backup_zip = zipfile.ZipFile(os.path.join(archive_folder, zip_filename), 'w')

   
    for folder_name, subfolders, filenames in os.walk(folder):
        backup_zip.write(folder_name)
        for filename in filenames:
            if filename.startswith(folder) and filename.endswith('.zip'):
                continue
            backup_zip.write(os.path.join(folder_name, filename))
    backup_zip.close()
