import os
import re
import shutil
from typing import Optional

from utils.fileio import load, save
from utils.puppeteer import browser_screenshot
from utils.str import to_camel_case


def get_all_packages(repo: str) -> list[str]:
    packages = [package for package in os.listdir(repo) if os.path.isdir(os.path.join(repo, package, 'src'))]
    packages.sort(key=lambda p: len(p), reverse=True)
    return packages


def norm_package(package: str) -> str:
    return ''.join(package.split('-')).lower()


def get_sbv_package(sbv: str, packages: list[str]) -> Optional[str]:
    for package in packages:
        if norm_package(package) in norm_package(sbv):
            return package


def copy_package(repo: str, src_pkg: str, tgt_pkg: str) -> None:
    src_pkg_path = os.path.join(repo, src_pkg)
    tgt_pkg_path = os.path.join(repo, tgt_pkg)

    shutil.copytree(os.path.join(src_pkg_path, 'src'), os.path.join(tgt_pkg_path, 'src'), dirs_exist_ok=True)
    if os.path.isfile(os.path.join(src_pkg_path, 'index.ts')):
        shutil.copy2(os.path.join(src_pkg_path, 'index.ts'), os.path.join(tgt_pkg_path, 'index.ts'))

    # Change meta title
    story_content = None
    for f in ['index.stories.ts', 'index.stories.tsx']:
        story_path = os.path.join(tgt_pkg_path, 'src', f)
        if os.path.isfile(story_path):
            story_content = load(story_path)
    if story_content is None:
        return
    story_content_lines = story_content.split('\n')
    title_line_pattern = r'\s*[\'"]?title[\'"]?\s*:\s*[\'"].*[\'"]\s*,?\s*'
    for i, line in enumerate(story_content_lines):
        if re.fullmatch(title_line_pattern, line):
            story_content_lines[i] = f"  title: 'Example/{to_camel_case(tgt_pkg)}',"
    save(story_path, '\n'.join(story_content_lines))


# async def storybook_screenshot(sbv_id: str,
#                                viewport: tuple[int, int],
#                                storybook_url: str = 'http://127.0.0.1:6006',
#                                exec_path: str = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
#                                ) -> str:
#     url = f'{storybook_url}/iframe.html?globals=&id={sbv_id}&viewMode=story'
#     return await browser_screenshot(url, viewport, exec_path)
