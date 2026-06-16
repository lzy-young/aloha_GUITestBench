import json
import requests
from GUIAgent.Aloha_Act.ui_aloha.act.gui_agent.llm.llm_utils import encode_image,is_image_path
import base64

# all hosted local models can be used as it
class UITarsAgent:
    def __init__(
        self,
        local_cua_model_url="http://localhost:8000",
        model_name="GUI-Owl-1.5-8B-Instruct",
        timeout_sec=120,
        logger=None,
        width=2560,
        height=1600
    ):
        self.local_cua_model_url = (local_cua_model_url or "http://localhost:8000").rstrip("/")
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self.logger = logger
        self.width=width
        self.height=height
    
    def _get_image_dimensions(self, image_path):
        from PIL import Image
        if not isinstance(image_path, str) or not is_image_path(image_path):
            return self.width, self.height
        try:
            with Image.open(image_path) as img:
                return img.size
        except Exception as e:
            if self.logger:
                self.logger.logger.error(f"Error getting image dimensions: {e}")
            return self.width, self.height

    def execute(self, instruction, screenshot_path, system_prompt, logging_dir):
        """Execute UI-TARS agent action"""
        
        # Prepare inputs
        screenshot_b64 = self._normalize_screenshot_to_base64(screenshot_path)
        prompted_message = self._get_prompt_grounding(instruction)
        self.width, self.height = self._get_image_dimensions(screenshot_path)
        try:
            # Log the prompts
            if self.logger:
                self.logger.log_text(prompted_message, "actor_uitars_prompt.log", logging_dir)
                self.logger.log_text(system_prompt, "actor_uitars_system.log", logging_dir)
                self.logger.log_json({
                    "instruction": str(instruction),
                    "local_cua_model_url": self.local_cua_model_url,
                    "model_name": self.model_name,
                }, "actor_uitars_request.json", logging_dir)
            
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": str(system_prompt)},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompted_message},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_b64}"
                                },
                            },
                        ],
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 256,
                "response_format": {"type": "json_object"},
            }

            # First try strict json_object mode; some local OpenAI-compatible servers may not support it.
            try:
                ui_tars_action = self._request_action_text(payload)
            except requests.HTTPError:
                payload.pop("response_format", None)
                ui_tars_action = self._request_action_text(payload)
            
            if self.logger:
                self.logger.log_text(ui_tars_action, "actor_uitars_raw_response.log", logging_dir)
            
            # Parse strict JSON output and normalize to executor schema.
            try:
                action_json = normalize_ui_tars_action_json(ui_tars_action, self.width, self.height)
            except Exception:
                # Retry once with a stronger schema reminder when model produced malformed JSON.
                repair_payload = dict(payload)
                repair_payload["messages"] = list(payload["messages"])
                repair_payload["messages"].append({
                    "role": "user",
                    "content": (
                        "Return exactly one JSON object only with fields needed by the action schema. "
                        "No markdown, no explanation, no extra objects."
                    ),
                })
                ui_tars_action = self._request_action_text(repair_payload)
                if self.logger:
                    self.logger.log_text(ui_tars_action, "actor_uitars_raw_response_retry.log", logging_dir)
                action_json = normalize_ui_tars_action_json(ui_tars_action, self.width, self.height)

            complete_flag = action_json.get("action") == "STOP"
            
            # Log the parsed action
            if self.logger:
                self.logger.log_json(action_json, "actor_uitars_parsed_action.json", logging_dir)
            
            return action_json, complete_flag
            
        except Exception as e:
            error_msg = f"Error processing UI-TARS response: {e}"
            if self.logger:
                self.logger.logger.error(error_msg)
                self.logger.log_error(e, {"mode": "ui-tars"}, target_dir=logging_dir)
            
            return {"action": "ERROR", "value": str(e), "position": [0, 0]}, False

    def _normalize_screenshot_to_base64(self, screenshot):
        if isinstance(screenshot, (bytes, bytearray)):
            return base64.b64encode(screenshot).decode("utf-8")
        if isinstance(screenshot, str):
            if screenshot.startswith("data:image/"):
                return screenshot.split(",", 1)[-1]
            if is_image_path(screenshot):
                return encode_image(screenshot)
            if self._looks_like_base64(screenshot):
                return screenshot
        return ""

    @staticmethod
    def _looks_like_base64(text: str) -> bool:
        if not isinstance(text, str) or not text:
            return False
        try:
            base64.b64decode(text, validate=True)
            return True
        except Exception:
            return False

    def _request_action_text(self, payload: dict) -> str:
        response = requests.post(
            self._chat_completion_url(),
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=self.timeout_sec,
        )
        response.raise_for_status()

        response_json = response.json()
        choices = response_json.get("choices") or []
        if not choices:
            raise ValueError("ui-tars response has no choices")

        message = (choices[0] or {}).get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            raw_content = content
        elif isinstance(content, list):
            raw_content = "\n".join(
                str(chunk.get("text", "")) if isinstance(chunk, dict) else str(chunk)
                for chunk in content
            )
        else:
            raw_content = str(content)

        return raw_content.strip()
    
    @staticmethod
    def _get_prompt_grounding(instruction):
        """Format instruction for UI-TARS - include both observation context and action"""
        if isinstance(instruction, dict):
            observation = instruction.get("Observation", "")
            action = instruction.get("Action", "")
            reasoning = instruction.get("Reasoning", "")
            # 如果 Action 为空/null，表示任务已完成，通知模型输出 STOP
            if not action or str(action).lower() in ('null', 'none', 'stop', 'done'):
                return "The task is completed. Output STOP action."
            if observation and action:
                return f"Current screen: {observation}\nAction to execute: {action}"
            return action or reasoning or str(instruction)
        return f"""{instruction}"""

    def _chat_completion_url(self) -> str:
        return f"{self.local_cua_model_url}/v1/chat/completions"


def convert_ui_tars_action_to_json(action_str: str, width: int, height: int) -> str:
    action_dict = normalize_ui_tars_action_json(action_str, width, height)
    return json.dumps(action_dict)


def _extract_first_json_object(text: str) -> dict:
    candidate = text.strip().replace("```json", "").replace("```", "").strip()
    if not candidate:
        raise ValueError("Empty UI-TARS response")

    decoder = json.JSONDecoder()
    starts = [i for i, ch in enumerate(candidate) if ch == "{"]
    for start in starts:
        try:
            obj, end = decoder.raw_decode(candidate[start:])
            tail = candidate[start + end :].strip()
            if isinstance(obj, dict) and (not tail):
                return obj
            if isinstance(obj, dict) and not tail.startswith("{"):
                return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("UI-TARS response is not a valid JSON object")


def _scale_xy(coord, width: int, height: int) -> list[int]:
    if not isinstance(coord, (list, tuple)) or len(coord) < 2:
        raise ValueError(f"Invalid coordinate: {coord}")
    x = float(coord[0])
    y = float(coord[1])

    # UI-TARS outputs normalized 0-1000 coordinates by default.
    if 0 <= x <= 1000 and 0 <= y <= 1000:
        return [int(x), int(y)]
    return [int(x), int(y)]


def normalize_ui_tars_action_json(action_str: str, width: int, height: int) -> dict:
    action_obj = _extract_first_json_object(action_str)

    if "action" not in action_obj:
        raise ValueError("UI-TARS JSON missing required field: action")

    raw_action = str(action_obj["action"]).strip().upper()
    alias_map = {
        "LEFT_CLICK": "CLICK",
        "RIGHT_CLICK": "LONG_PRESS",
        "TYPE": "INPUT",
        "FINISHED": "STOP",
        "CALL_USER": "STOP",
    }
    action = alias_map.get(raw_action, raw_action)

    output = {
        "action": action,
        "value": None,
        "position": None,
    }

    point_actions = ["CLICK", "LONG_PRESS", "DOUBLE_CLICK"]
    if action in point_actions:
        if "position" not in action_obj:
            raise ValueError(f"{action} requires field: position")
        output["position"] = _scale_xy(action_obj["position"], width, height)
        return output

    if action == "INPUT":
        if "value" not in action_obj:
            raise ValueError("INPUT requires field: value")
        output["value"] = str(action_obj["value"])
        return output

    if action == "SCROLL":
        if "direction" in action_obj:
            output["direction"] = str(action_obj["direction"]).lower()
        elif "value" in action_obj:
            # 旧格式：value 正数=上滑，负数=下滑
            output["direction"] = "up" if int(float(action_obj["value"])) > 0 else "down"
        else:
            output["direction"] = "down"
        if "position" in action_obj and action_obj["position"] is not None:
            output["position"] = _scale_xy(action_obj["position"], width, height)
        return output

    if action == "SWIPE":
        if "direction" in action_obj:
            direction = str(action_obj["direction"]).lower()
        else:
            direction = "left"
        # SWIPE up/down → convert to SCROLL (vertical navigation)
        if direction in ["up", "down"]:
            output["action"] = "SCROLL"
            output["direction"] = direction
        else:
            output["direction"] = direction
        return output

    if action in ["DRAG", "DRAG_AND_DROP"]:
        if "touch_xy" not in action_obj or "lift_xy" not in action_obj:
            raise ValueError(f"{action} requires fields: touch_xy and lift_xy")
        output["action"] = "DRAG_AND_DROP"
        output["touch_xy"] = _scale_xy(action_obj["touch_xy"], width, height)
        output["lift_xy"] = _scale_xy(action_obj["lift_xy"], width, height)
        return output

    if action in ["BACK", "HOME", "ENTER", "WAIT", "STOP"]:
        return output

    if action == "OPEN_APP":
        if "app_name" not in action_obj:
            raise ValueError("OPEN_APP requires field: app_name")
        output["app_name"] = str(action_obj["app_name"])
        return output

    if action == "ANSWER":
        return {"action": "STOP", "value": action_obj.get("value", "")}
    if action == "PRESS":
        # UI-TARS may output "button" or "key" field
        key = action_obj.get("button", "") or action_obj.get("key", "")
        key_lower = str(key).strip().lower()
        if key_lower == "enter":
            return {"action": "ENTER"}
        # Map common key names to Android KEYCODE_ format
        _keycode_map = {
            "backspace": "KEYCODE_DEL",
            "delete": "KEYCODE_DEL",
            "del": "KEYCODE_DEL",
            "tab": "KEYCODE_TAB",
            "space": "KEYCODE_SPACE",
            "escape": "KEYCODE_ESCAPE",
            "esc": "KEYCODE_ESCAPE",
            "home": "KEYCODE_HOME",
            "back": "KEYCODE_BACK",
            "search": "KEYCODE_SEARCH",
            "menu": "KEYCODE_MENU",
            "volume_up": "KEYCODE_VOLUME_UP",
            "volume_down": "KEYCODE_VOLUME_DOWN",
        }
        keycode = _keycode_map.get(key_lower, f"KEYCODE_{key_lower.upper()}")
        return {"action": "PRESS", "keycode": keycode}

    raise ValueError(f"Unsupported UI-TARS action: {action}")

