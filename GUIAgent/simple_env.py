import os
import time
import io
import re
import contextlib
import subprocess
import xml.etree.ElementTree as ET
from typing import Optional
from PIL import Image

from core.data_model import EnvParams


class SimpleAdbEnv:
    """不依赖 android_env 的简易 ADB 环境。
    
    所有操作直接调用 adb 命令，截图、获取 UI 元素、执行动作均通过 subprocess 完成。
    兼容 GUITestBench 的 BaseEnviron 接口。
    """

    def __init__(self, console_port: int, adb_path: str):
        self._console_port = console_port
        self._adb_path = adb_path
        self._emulator_id = f"emulator-{console_port}"
        self.controller = self  # 控制器就是自己
        self.logical_screen_size = self._get_screen_size()
        w, h = self.logical_screen_size
        self.physical_frame_boundary = (0, 0, w, h)
        self.orientation = 0

        # 启动时确保 ADB server 在运行
        self._adb(["devices"])

    # ─── ADB 命令执行 ─────────────────────────

    def _adb(self, args: list[str], timeout: int = 30) -> str:
        """执行 adb 命令，返回 stdout。"""
        cmd = [self._adb_path, "-s", self._emulator_id] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(
                f"ADB error: {' '.join(cmd)}\n{result.stderr or result.stdout}"
            )
        return result.stdout

    def _adb_device(self, args: list[str], timeout: int = 30) -> str:
        """执行不指定设备的 adb 命令。"""
        cmd = [self._adb_path] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(
                f"ADB error: {' '.join(cmd)}\n{result.stderr or result.stdout}"
            )
        return result.stdout

    def execute_adb_call(self, request) -> "_AdbResponse":
        """执行 protobuf 格式的 ADB 请求。"""
        command_type = request.WhichOneof("command")
        timeout = request.timeout_sec or 30

        if command_type == "generic":
            args = list(request.generic.args)
            return self._exec(args, timeout)

        elif command_type == "install_apk":
            install = request.install_apk
            loc = install.WhichOneof("location")
            if loc == "filesystem":
                fpath = install.filesystem.path
                return self._exec(["install", "-r", "-t", "-g", fpath], timeout)
            elif loc == "blob":
                import tempfile
                f = tempfile.NamedTemporaryFile(suffix=".apk", delete=False)
                fpath = f.name
                f.write(install.blob.contents)
                f.close()
                result = self._exec(["install", "-r", "-t", "-g", fpath], timeout)
                os.unlink(fpath)
                return result

        elif command_type == "tap":
            return self._exec(
                ["shell", "input", "tap", str(request.tap.x), str(request.tap.y)],
                timeout,
            )

        elif command_type == "input_text":
            return self._exec(
                ["shell", "input", "text", request.input_text.text], timeout
            )

        elif command_type == "press_button":
            keycode = request.press_button.button
            return self._exec(["shell", "input", "keyevent", str(keycode)], timeout)

        elif command_type == "uninstall_package":
            return self._exec(
                ["uninstall", request.uninstall_package.package_name], timeout
            )

        elif command_type == "start_activity":
            return self._exec(
                ["shell", "am", "start", "-W", "-n",
                 request.start_activity.full_activity],
                timeout,
            )

        elif command_type == "settings":
            s = request.settings
            from android_env.proto import adb_pb2
            ns = adb_pb2.AdbRequest.SettingsRequest.Namespace.Name(
                s.name_space
            ).lower()
            verb = s.WhichOneof("verb")
            if verb == "put":
                return self._exec(
                    ["shell", "settings", "put", ns, s.put.key, s.put.value], timeout
                )
            elif verb == "get":
                return self._exec(
                    ["shell", "settings", "get", ns, s.get.key], timeout
                )

        elif command_type == "dumpsys":
            return self._exec(
                ["shell", "dumpsys", request.dumpsys.service], timeout
            )

        elif command_type == "package_manager":
            pm = request.package_manager
            verb = pm.WhichOneof("verb")
            if verb == "list":
                what = pm.list.WhichOneof("what")
                return self._exec(["shell", "pm", "list", what], timeout)
            elif verb == "clear":
                return self._exec(
                    ["shell", "pm", "clear", pm.clear.package_name], timeout
                )
            elif verb == "grant":
                for perm in pm.grant.permissions:
                    self._exec(
                        ["shell", "pm", "grant", pm.grant.package_name, perm],
                        timeout,
                    )
                return _AdbResponse.ok()

        # 兜底
        return self._exec([], timeout)

    def _exec(self, args, timeout) -> "_AdbResponse":
        """执行 adb 命令并封装成 AdbResponse 格式。"""
        from android_env.proto import adb_pb2
        resp = adb_pb2.AdbResponse()
        if not args:
            resp.status = adb_pb2.AdbResponse.Status.OK
            return resp

        cmd = [self._adb_path, "-s", self._emulator_id] + args
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            output = result.stdout + result.stderr
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
            resp.status = adb_pb2.AdbResponse.Status.OK
            resp.generic.output = output
            return resp
        except subprocess.CalledProcessError as e:
            resp.status = adb_pb2.AdbResponse.Status.ADB_ERROR
            resp.error_message = e.output or str(e)
            resp.generic.output = e.output or b""
            return resp
        except Exception as e:
            resp.status = adb_pb2.AdbResponse.Status.INTERNAL_ERROR
            resp.error_message = str(e)
            return resp

    # ─── 截图 ────────────────────────────────

    def get_state(self, wait_to_stabilize: bool = True):
        """截图 + 获取 UI 元素，模拟 android_env 的 get_state 接口。"""
        if wait_to_stabilize:
            time.sleep(0.5)

        # 截图
        raw = subprocess.check_output(
            [self._adb_path, "-s", self._emulator_id, "exec-out", "screencap", "-p"],
            timeout=15,
        )
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        ui_elements = self._get_ui_elements()

        return _SimpleState(img, ui_elements, self.logical_screen_size)

    # ─── UI 元素获取 ─────────────────────────

    def _get_ui_elements(self):
        """通过 uiautomator dump 获取 UI 元素。"""
        try:
            self._adb(
                ["shell", "uiautomator", "dump", "/sdcard/ui.xml"], timeout=15
            )
            raw = subprocess.check_output(
                [self._adb_path, "-s", self._emulator_id, "shell", "cat", "/sdcard/ui.xml"],
                timeout=10,
            )
            return self._parse_ui_xml(raw)
        except Exception:
            return []

    def _parse_ui_xml(self, raw: bytes):
        elements = []
        try:
            text = raw.decode("utf-8", errors="replace")
            xml_start = text.find("<?xml")
            if xml_start >= 0:
                text = text[xml_start:]
            root = ET.fromstring(text)
            for node in root.iter("node"):
                bounds = node.get("bounds", "")
                class_name = node.get("class", "")
                text_content = node.get("text", "") or ""
                content_desc = node.get("content-desc", "") or ""
                cd = self._parse_bounds(bounds)
                if cd:
                    el = _UIElement(
                        x1=cd[0], y1=cd[1], x2=cd[2], y2=cd[3],
                        text=text_content,
                        content_description=content_desc,
                        class_name=class_name,
                        hint_text=node.get("hint", "") or "",
                        is_editable=node.get("enabled", "true") == "true"
                        and "EditText" in class_name,
                    )
                    # Set bbox_pixels for SoM visualization
                    BBox = type("BBox", (), {"x_min": cd[0], "y_min": cd[1], "x_max": cd[2], "y_max": cd[3]})
                    el.bbox_pixels = BBox()
                    elements.append(el)
        except Exception:
            pass
        return elements

    def _parse_bounds(self, s: str):
        m = re.findall(r"\[(\d+),(\d+)\]", s)
        if len(m) == 2:
            return (int(m[0][0]), int(m[0][1]), int(m[1][0]), int(m[1][1]))
        return None

    # ─── 设备信息 ────────────────────────────

    def _get_screen_size(self):
        try:
            out = self._adb(["shell", "wm", "size"], timeout=5)
            m = re.search(r"(\d+)x(\d+)", out)
            if m:
                return (int(m.group(1)), int(m.group(2)))
        except Exception:
            pass
        return (1080, 2400)

    def reset(self, go_home: bool = True):
        if go_home:
            try:
                self._adb(
                    [
                        "shell", "am", "start", "-W",
                        "-n",
                        "com.google.android.apps.nexuslauncher/.NexusLauncherActivity",
                    ],
                    timeout=10,
                )
            except Exception:
                pass

    @contextlib.contextmanager
    def pull_file(self, remote_path: str, timeout_sec: int = 30):
        """Pull a directory from device to a temp directory (context manager).
        
        Matches AndroidWorldController.pull_file behavior: pulls the parent
        directory of the given path so the caller can find the file by name
        inside the returned temp directory.
        
        The pulled files are placed directly in tmp_dir (not in a subdirectory),
        matching the behavior of AndroidWorldController's tmp_directory_from_device.
        """
        import tempfile
        import shutil
        remote_dir = os.path.dirname(remote_path)
        tmp_dir = tempfile.mkdtemp()
        try:
            # adb pull creates a subdirectory named after the remote dir basename.
            # We pull into a staging area then move contents up to match
            # AndroidWorldController behavior (files directly in tmp_dir).
            staging = tempfile.mkdtemp()
            try:
                self._adb(["pull", remote_dir, staging], timeout=timeout_sec)
                # adb pull puts files under staging/<basename>/
                pulled_dir = os.path.join(staging, os.path.basename(remote_dir))
                if os.path.isdir(pulled_dir):
                    for item in os.listdir(pulled_dir):
                        import shutil as _shutil
                        _shutil.move(
                            os.path.join(pulled_dir, item),
                            os.path.join(tmp_dir, item),
                        )
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            yield tmp_dir
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def push_file(self, local_path: str, remote_path: str, timeout_sec: int = 30):
        """Push a local file to the device."""
        self._adb(["push", local_path, remote_path], timeout=timeout_sec)

    def close(self):
        pass

    def __del__(self):
        self.close()


class _SimpleState:
    def __init__(self, pixels, ui_elements, logical_screen_size):
        self.pixels = pixels
        self.ui_elements = ui_elements
        self._logical_screen_size = logical_screen_size


class _UIElement:
    def __init__(self, x1=0, y1=0, x2=0, y2=0,
                 text="", content_description="", class_name="",
                 hint_text="", is_editable=False, resource_name="",
                 is_checked=False, is_checkable=False, is_clickable=False,
                 is_enabled=True, is_focused=False, is_focusable=False,
                 is_scrollable=False, is_selected=False):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.text = text
        self.content_description = content_description
        self.class_name = class_name
        self.hint_text = hint_text
        self.is_editable = is_editable
        self.is_checked = is_checked
        self.is_checkable = is_checkable
        self.is_clickable = is_clickable
        self.is_enabled = is_enabled
        self.is_focused = is_focused
        self.is_focusable = is_focusable
        self.is_scrollable = is_scrollable
        self.is_selected = is_selected
        self.resource_name = resource_name
        self.is_visible = True
        # Bounding box for Set-of-Marks (SoM) visualization
        self.bbox_pixels = None


class FakeResponse:
    """占位 response，环境初始化时不会执行到需要真正 response 的地方。"""
    status = 0
