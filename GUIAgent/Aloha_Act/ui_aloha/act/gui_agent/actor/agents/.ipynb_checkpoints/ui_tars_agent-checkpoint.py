import json
import requests
from ui_aloha.act.gui_agent.llm.llm_utils import encode_image


# all hosted local models can be used as it
class UITarsAgent:
    def __init__(
        self,
        local_cua_model_url="http://localhost:8000",
        model_name="GUI-Owl-1.5-8B-Instruct",
        timeout_sec=120,
        logger=None,
    ):
        self.local_cua_model_url = (local_cua_model_url or "http://localhost:8000").rstrip("/")
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self.logger = logger
        self.width=2560
        self.height=1600
    
    def execute(self, instruction, screenshot_path, system_prompt, logging_dir):
        """Execute UI-TARS agent action"""
        
        # Prepare inputs
        screenshot_b64 = encode_image(screenshot_path)
        prompted_message = self._get_prompt_grounding(instruction)
        
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
            }

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

            ui_tars_action = raw_content.strip()
            
            if self.logger:
                self.logger.log_text(ui_tars_action, "actor_uitars_raw_response.log", logging_dir)
            
            # Parse strict JSON output and normalize to executor schema.
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
    
    @staticmethod
    def _get_prompt_grounding(instruction):
        """Format instruction for UI-TARS - no need to prompt for ui-tars"""
        if isinstance(instruction, dict):
            instruction = instruction.get("Action") or instruction.get("Reasoning") or str(instruction)
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
        return [int(x / 1000 * width), int(y / 1000 * height)]
    return [int(x), int(y)]


def normalize_ui_tars_action_json(action_str: str, width: int, height: int) -> dict:
    action_obj = _extract_first_json_object(action_str)

    if "action" not in action_obj:
        raise ValueError("UI-TARS JSON missing required field: action")

    raw_action = str(action_obj["action"]).strip().upper()
    alias_map = {
        "MOUSE_MOVE": "MOVE",
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

    point_actions = {"CLICK", "RIGHT_CLICK", "DOUBLE_CLICK", "TRIPLE_CLICK", "MOVE"}
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
        if "value" not in action_obj:
            raise ValueError("SCROLL requires field: value")
        output["value"] = int(float(action_obj["value"]))
        if "position" in action_obj and action_obj["position"] is not None:
            output["position"] = _scale_xy(action_obj["position"], width, height)
        return output

    if action == "DRAG":
        if "from" not in action_obj or "to" not in action_obj:
            raise ValueError("DRAG requires fields: from and to")
        start = _scale_xy(action_obj["from"], width, height)
        end = _scale_xy(action_obj["to"], width, height)
        output["from"] = start
        output["to"] = end
        output["start"] = start
        output["end"] = end
        return output

    if action in {"HOTKEY", "KEY"}:
        if "value" not in action_obj:
            raise ValueError("HOTKEY requires field: value")
        if output["value"] == "enter":
            output["action"]= "ENTER"
            return output
        elif output["value"] == "esc":
            output["action"]= "ESC"
            return output
        output["action"] = "HOTKEY"
        output["value"] = action_obj["value"]
        return output

    if action in {"ENTER", "ESC", "WAIT", "STOP"}:
        return output

    raise ValueError(f"Unsupported UI-TARS action: {action}")