# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: Apache-2.0
import re
import ast
import math
import json

from utils.re_func import extract_action_content
from utils.ui_tars_scroll_utils import ui_tars_scroll_to_browsergym

IMAGE_FACTOR = 28
MIN_PIXELS = 100 * 28 * 28
MAX_PIXELS = 16384 * 28 * 28
MAX_RATIO = 200
ANDROID_HEIGHT = 2400
ANDROID_WIDTH = 1080



key_mapping = {
    'backquote': 'Backquote',
    'ctrl': 'Control',
    'shift': 'Shift',
    'meta': 'Meta',
    'shiftleft': 'ShiftLeft',
    'alt': 'Alt',
    'tab': 'Tab',
    'enter': 'Enter',
    'space': 'Space',
    'backspace': 'Backspace',
    'delete': 'Delete',
    'escape': 'Escape',
    'home': 'Home',
    'end': 'End',
    'minus': 'Minus',
    'equal': 'Equal',
    'insert': 'Insert',
    'pageup': 'PageUp',
    'pagedown': 'PageDown',
    'up': 'ArrowUp',
    'down': 'ArrowDown',
    'left': 'ArrowLeft',
    'right': 'ArrowRight',
    'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4', 'f5': 'F5',
    'f6': 'F6', 'f7': 'F7', 'f8': 'F8', 'f9': 'F9', 'f10': 'F10',
    'f11': 'F11', 'f12': 'F12'
}


def convert_point_to_coordinates(text, is_answer=False):
    
    pattern = r"<point>(\d+)\s+(\d+)</point>"

    def replace_match(match):
        x1, y1 = map(int, match.groups())
        x = (x1 + x1) // 2  
        y = (y1 + y1) // 2  
        if is_answer:
            return f"({x},{y})"  
        return f"({x},{y})"  

    
    text = re.sub(r"\[EOS\]", "", text)
    return re.sub(pattern, replace_match, text).strip()



def parse_action(action_str):
    try:
        
        node = ast.parse(action_str, mode='eval')

        
        if not isinstance(node, ast.Expression):
            raise ValueError("Not an expression")

        
        call = node.body

        
        if not isinstance(call, ast.Call):
            raise ValueError("Not a function call")

        
        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            func_name = call.func.attr
        else:
            func_name = None

        
        kwargs = {}
        for kw in call.keywords:
            key = kw.arg
            
            if isinstance(kw.value, ast.Constant):
                value = kw.value.value
            elif isinstance(kw.value, ast.Str):  
                value = kw.value.s
            else:
                value = None
            kwargs[key] = value

        return {'function': func_name, 'args': kwargs}

    except Exception as e:
        print(f"Failed to parse action '{action_str}': {e}")
        return None


def escape_single_quotes(text):
    
    pattern = r"(?<!\\)'"
    return re.sub(pattern, r"\\'", text)


def round_by_factor(number: int, factor: int) -> int:
    """Returns the closest integer to 'number' that is divisible by 'factor'."""
    return round(number / factor) * factor


def ceil_by_factor(number: int, factor: int) -> int:
    """Returns the smallest integer greater than or equal to 'number' that is divisible by 'factor'."""
    return math.ceil(number / factor) * factor


def floor_by_factor(number: int, factor: int) -> int:
    """Returns the largest integer less than or equal to 'number' that is divisible by 'factor'."""
    return math.floor(number / factor) * factor


def linear_resize(height: int,
                  width: int,
                  factor: int = IMAGE_FACTOR,
                  min_pixels: int = MIN_PIXELS,
                  max_pixels: int = MAX_PIXELS) -> tuple[int, int]:
    if width * height > max_pixels:
        
        resize_factor = math.sqrt(max_pixels / (width * height))
        width, height = int(width * resize_factor), int(height * resize_factor)
    if width * height < min_pixels:
        resize_factor = math.sqrt(min_pixels / (width * height))
        width, height = math.ceil(width * resize_factor), math.ceil(
            height * resize_factor)

    return height, width


def smart_resize(height: int,
                 width: int,
                 factor: int = IMAGE_FACTOR,
                 min_pixels: int = MIN_PIXELS,
                 max_pixels: int = MAX_PIXELS) -> tuple[int, int]:
    """
    Rescales the image so that the following conditions are met:

    1. Both dimensions (height and width) are divisible by 'factor'.

    2. The total number of pixels is within the range ['min_pixels', 'max_pixels'].

    3. The aspect ratio of the image is maintained as closely as possible.
    """
    if max(height, width) / min(height, width) > MAX_RATIO:
        raise ValueError(
            f"absolute aspect ratio must be smaller than {MAX_RATIO}, got {max(height, width) / min(height, width)}"
        )
    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    return h_bar, w_bar


def parse_action_to_structure_output(text,
                                     factor,
                                     origin_resized_height,
                                     origin_resized_width,
                                     model_type="qwen25vl",
                                     max_pixels=16384 * 28 * 28,
                                     min_pixels=100 * 28 * 28):
    text = text.strip()

    if "<point>" in text:
        text = convert_point_to_coordinates(text)
    if "start_point=" in text:
        text = text.replace("start_point=", "start_box=")
    if "end_point=" in text:
        text = text.replace("end_point=", "end_box=")
    if "point=" in text:
        text = text.replace("point=", "start_box=")

    if model_type == "qwen25vl":
        smart_resize_height, smart_resize_width = smart_resize(
            origin_resized_height,
            origin_resized_width,
            factor=IMAGE_FACTOR,
            min_pixels=min_pixels,
            max_pixels=max_pixels)
    
   
    if text.startswith("Thought:"):
        thought_pattern = r"Thought: (.+?)(?=\s*Action: |$)"
        thought_hint = "Thought: "
    elif text.startswith("Reflection:"):
        thought_pattern = r"Reflection: (.+?)Action_Summary: (.+?)(?=\s*Action: |$)"
        thought_hint = "Reflection: "
    elif text.startswith("Action_Summary:"):
        thought_pattern = r"Action_Summary: (.+?)(?=\s*Action: |$)"
        thought_hint = "Action_Summary: "
    else:
        thought_pattern = r"Thought: (.+?)(?=\s*Action: |$)"
        thought_hint = "Thought: "
    reflection, thought = None, None
    thought_match = re.search(thought_pattern, text, re.DOTALL)
    if thought_match:
        if len(thought_match.groups()) == 1:
            thought = thought_match.group(1).strip()
        elif len(thought_match.groups()) == 2:
            thought = thought_match.group(2).strip()
            reflection = thought_match.group(1).strip()
    
    if "Action:" not in text:
        raise ValueError("Text does not contain 'Action:'")
    
    
    # action_str = text.split("Action: ")[-1]
    action_str = extract_action_content(text)

    tmp_all_action = action_str.split(")\n\n")
    all_action = []
    
    for action_str in tmp_all_action:
        if "type(content" in action_str:
            if not action_str.strip().endswith(")"):
                action_str = action_str.strip() + ")"
            
            def escape_quotes(match):
                content = match.group(1)  
                return content

            
            pattern = r"type\(content='(.*?)'\)"  
            if re.search(pattern, action_str):  
                content = re.sub(pattern, escape_quotes, action_str)
            else:
                raise ValueError("Pattern not found in the input string.")

            
            action_str = escape_single_quotes(content)
            action_str = "type(content='" + action_str + "')"
        if not action_str.strip().endswith(")"):
            action_str = action_str.strip() + ")"
        all_action.append(action_str)

    parsed_actions = [
        parse_action(action.replace("\n", "\\n").lstrip())
        for action in all_action
    ]
    actions = []
    
    """
    Traceback (most recent call last):
    File "/Users/figogao/Desktop/GUITester/eval.py", line 50, in <module>
        env.run()
    File "/Users/figogao/Desktop/GUITester/environment.py", line 248, in run
        android_format_action = self.agent.call(observation=self.observation)
                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File "/Users/figogao/Desktop/GUITester/uitars.py", line 212, in call
        return self.parse_response(raw_response)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File "/Users/figogao/Desktop/GUITester/uitars.py", line 170, in parse_response
        parsed_dict = parse_action_to_structure_output(
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File "/Users/figogao/Desktop/GUITester/utils/ui_tars_action_parser.py", line 275, in parse_action_to_structure_output
        raise ValueError(f"Action can't parse: {raw_str}")
    ValueError: Action can't parse: finished(content='Create a new task named \\'Keep smile\\' and clear all completed tasks.')
    """
    
    for action_instance, raw_str in zip(parsed_actions, all_action):
        if action_instance == None:
            print(f"Action can't parse: {raw_str}")
            raise ValueError(f"Action can't parse: {raw_str}")
        action_type = action_instance["function"]
        params = action_instance["args"]

        # import pdb; pdb.set_trace()
        action_inputs = {}
        for param_name, param in params.items():
            if param == "": continue
            param = param.lstrip() 
            
            action_inputs[param_name.strip()] = param

            if "start_box" in param_name or "end_box" in param_name:
                ori_box = param
                # Remove parentheses and split the string by commas
                numbers = ori_box.replace("(", "").replace(")", "").split(",")

                # Convert to float and scale by 1000
                # Qwen2.5vl output absolute coordinates, qwen2vl output relative coordinates
                if model_type == "qwen25vl":
                    float_numbers = []
                    for num_idx, num in enumerate(numbers):
                        num = float(num)
                        if (num_idx + 1) % 2 == 0:
                            float_numbers.append(
                                float(num / smart_resize_height))
                        else:
                            float_numbers.append(
                                float(num / smart_resize_width))
                else:
                    if '<point>x1 y1</point>' in numbers:
                        continue
                    float_numbers = [float(num) / factor for num in numbers]

                if len(float_numbers) == 2:
                    float_numbers = [
                        float_numbers[0], float_numbers[1], float_numbers[0],
                        float_numbers[1]
                    ]
                action_inputs[param_name.strip()] = str(float_numbers)
        
        # import pdb; pdb.set_trace()
        actions.append({
            "reflection": reflection,
            "thought": thought,
            "action_type": action_type,
            "action_inputs": action_inputs,
            "text": text
        })
    return actions


def parsing_response_to_pyautogui_code(responses,
                                       image_height: int,
                                       image_width: int,
                                       input_swap: bool = True) -> str:
   

    pyautogui_code = f"import pyautogui\nimport time\n"
    if isinstance(responses, dict):
        responses = [responses]
    for response_id, response in enumerate(responses):
        if "observation" in response:
            observation = response["observation"]
        else:
            observation = ""

        if "thought" in response:
            thought = response["thought"]
        else:
            thought = ""

        if response_id == 0:
            pyautogui_code += f"'''\nObservation:\n{observation}\n\nThought:\n{thought}\n'''\n"
        else:
            pyautogui_code += f"\ntime.sleep(1)\n"

        action_dict = response
        action_type = action_dict.get("action_type")
        action_inputs = action_dict.get("action_inputs", {})

        if action_type == "hotkey":
            # Parsing hotkey action
            if "key" in action_inputs:
                hotkey = action_inputs.get("key", "")
            else:
                hotkey = action_inputs.get("hotkey", "")

            if hotkey == "arrowleft":
                hotkey = "left"

            elif hotkey == "arrowright":
                hotkey = "right"

            elif hotkey == "arrowup":
                hotkey = "up"

            elif hotkey == "arrowdown":
                hotkey = "down"

            if hotkey:
                # Handle other hotkeys
                keys = hotkey.split()  # Split the keys by space
                convert_keys = []
                for key in keys:
                    if key == "space":
                        key = ' '
                    convert_keys.append(key)
                pyautogui_code += f"\npyautogui.hotkey({', '.join([repr(k) for k in convert_keys])})"

        elif action_type in ["press", "keydown"]:
            # Parsing press action
            if "key" in action_inputs:
                key_to_press = action_inputs.get("key", "")
            else:
                key_to_press = action_inputs.get("press", "")

            if key_to_press == "arrowleft":
                key_to_press = "left"

            elif key_to_press == "arrowright":
                key_to_press = "right"

            elif key_to_press == "arrowup":
                key_to_press = "up"

            elif key_to_press == "arrowdown":
                key_to_press = "down"

            elif key_to_press == "space":
                key_to_press = " "

            if key_to_press:
                # Simulate pressing a single key
                pyautogui_code += f"\npyautogui.keyDown({repr(key_to_press)})"

        elif action_type in ["release", "keyup"]:
            # Parsing press action
            if "key" in action_inputs:
                key_to_press = action_inputs.get("key", "")
            else:
                key_to_press = action_inputs.get("press", "")

            if key_to_press == "arrowleft":
                key_to_press = "left"

            elif key_to_press == "arrowright":
                key_to_press = "right"

            elif key_to_press == "arrowup":
                key_to_press = "up"

            elif key_to_press == "arrowdown":
                key_to_press = "down"

            elif key_to_press == "space":
                key_to_press = " "

            if key_to_press:
                # Simulate pressing a single key
                pyautogui_code += f"\npyautogui.keyUp({repr(key_to_press)})"

        elif action_type == "type":
            # Parsing typing action using clipboard
            content = action_inputs.get("content", "")
            content = escape_single_quotes(content)
            stripped_content = content
            if content.endswith("\n") or content.endswith("\\n"):
                stripped_content = stripped_content.rstrip("\\n").rstrip("\n")
            if content:
                if input_swap:
                    pyautogui_code += f"\nimport pyperclip"
                    pyautogui_code += f"\npyperclip.copy('{stripped_content}')"
                    pyautogui_code += f"\npyautogui.hotkey('ctrl', 'v')"
                    pyautogui_code += f"\ntime.sleep(0.5)\n"
                    if content.endswith("\n") or content.endswith("\\n"):
                        pyautogui_code += f"\npyautogui.press('enter')"
                else:
                    pyautogui_code += f"\npyautogui.write('{stripped_content}', interval=0.1)"
                    pyautogui_code += f"\ntime.sleep(0.5)\n"
                    if content.endswith("\n") or content.endswith("\\n"):
                        pyautogui_code += f"\npyautogui.press('enter')"

        elif action_type in ["drag", "select"]:
            # Parsing drag or select action based on start and end_boxes
            start_box = action_inputs.get("start_box")
            end_box = action_inputs.get("end_box")
            if start_box and end_box:
                x1, y1, x2, y2 = eval(
                    start_box)  # Assuming box is in [x1, y1, x2, y2]
                sx = round(float((x1 + x2) / 2) * image_width, 3)
                sy = round(float((y1 + y2) / 2) * image_height, 3)
                x1, y1, x2, y2 = eval(
                    end_box)  # Assuming box is in [x1, y1, x2, y2]
                ex = round(float((x1 + x2) / 2) * image_width, 3)
                ey = round(float((y1 + y2) / 2) * image_height, 3)
                pyautogui_code += (
                    f"\npyautogui.moveTo({sx}, {sy})\n"
                    f"\npyautogui.dragTo({ex}, {ey}, duration=1.0)\n")

        elif action_type == "scroll":
            # Parsing scroll action
            start_box = action_inputs.get("start_box")
            if start_box:
                x1, y1, x2, y2 = eval(
                    start_box)  # Assuming box is in [x1, y1, x2, y2]
                x = round(float((x1 + x2) / 2) * image_width, 3)
                y = round(float((y1 + y2) / 2) * image_height, 3)

                
                # pyautogui_code += f"\npyautogui.click({x}, {y}, button='left')"
            else:
                x = None
                y = None
            direction = action_inputs.get("direction", "")

            if x == None:
                if "up" in direction.lower():
                    pyautogui_code += f"\npyautogui.scroll(5)"
                elif "down" in direction.lower():
                    pyautogui_code += f"\npyautogui.scroll(-5)"
            else:
                if "up" in direction.lower():
                    pyautogui_code += f"\npyautogui.scroll(5, x={x}, y={y})"
                elif "down" in direction.lower():
                    pyautogui_code += f"\npyautogui.scroll(-5, x={x}, y={y})"

        elif action_type in [
                "click", "left_single", "left_double", "right_single", "hover"
        ]:
            # Parsing mouse click actions
            start_box = action_inputs.get("start_box")
            start_box = str(start_box)
            if start_box:
                start_box = eval(start_box)
                if len(start_box) == 4:
                    x1, y1, x2, y2 = start_box  # Assuming box is in [x1, y1, x2, y2]
                elif len(start_box) == 2:
                    x1, y1 = start_box
                    x2 = x1
                    y2 = y1
                x = round(float((x1 + x2) / 2) * image_width, 3)
                y = round(float((y1 + y2) / 2) * image_height, 3)
                if action_type == "left_single" or action_type == "click":
                    pyautogui_code += f"\npyautogui.click({x}, {y}, button='left')"
                elif action_type == "left_double":
                    pyautogui_code += f"\npyautogui.doubleClick({x}, {y}, button='left')"
                elif action_type == "right_single":
                    pyautogui_code += f"\npyautogui.click({x}, {y}, button='right')"
                elif action_type == "hover":
                    pyautogui_code += f"\npyautogui.moveTo({x}, {y})"

        elif action_type in ["finished"]:
            pyautogui_code = f"DONE"

        else:
            pyautogui_code += f"\n# Unrecognized action type: {action_type}"

    return pyautogui_code


def parsing_response_to_browsergym_format(
    responses, 
    image_height: int,
    image_width: int,
    magnitude: int = 100,
    click_before_scroll: bool = False
) -> list[str]:
    
    if isinstance(responses, dict):
        responses = [responses]
    
    browsergym_actions = []
    for response in responses:
        action_dict = response
        action_type = action_dict.get("action_type")
        action_inputs = action_dict.get("action_inputs", {})
        
        if action_type in ["click", "left_double", "right_single"]: 
            # Parsing mouse click actions
            start_box = action_inputs.get("start_box")
            start_box = str(start_box)
            if start_box:
                start_box = eval(start_box)
                if len(start_box) == 4:
                    x1, y1, x2, y2 = start_box  # Assuming box is in [x1, y1, x2, y2]
                elif len(start_box) == 2:
                    x1, y1 = start_box
                    x2 = x1
                    y2 = y1
                x = round(float((x1 + x2) / 2) * image_width, 3)
                y = round(float((y1 + y2) / 2) * image_height, 3)

                if action_type == 'click':
                    browsergym_actions.append(f"mouse_click({x}, {y}, 'left')")
                elif action_type == 'left_double':
                    browsergym_actions.append(f"mouse_dblclick({x}, {y}, 'left')")
                elif action_type == 'right_single':
                    browsergym_actions.append(f"mouse_click_right({x}, {y})")
        
        elif action_type == 'drag':
            # Parsing drag or select action based on start and end_boxes
            start_box = action_inputs.get("start_box")
            end_box = action_inputs.get("end_box")
            if start_box and end_box:
                x1, y1, x2, y2 = eval(
                    start_box)  # Assuming box is in [x1, y1, x2, y2]
                sx = round(float((x1 + x2) / 2) * image_width, 3)
                sy = round(float((y1 + y2) / 2) * image_height, 3)
                x1, y1, x2, y2 = eval(
                    end_box)  # Assuming box is in [x1, y1, x2, y2]
                ex = round(float((x1 + x2) / 2) * image_width, 3)
                ey = round(float((y1 + y2) / 2) * image_height, 3)
                browsergym_actions.append(f"mouse_drag_and_drop({sx}, {sy}, {ex}, {ey})")
        
        elif action_type == 'type':
            # Parsing typing action using clipboard
            content = action_inputs.get("content", "")
            content = escape_single_quotes(content)
            stripped_content = content
            if content.endswith("\n") or content.endswith("\\n"):
                stripped_content = stripped_content.rstrip("\\n").rstrip("\n")
            if content:
                browsergym_actions.append(f"keyboard_type('{stripped_content}')")
        
        elif action_type == 'hotkey':
            # Parsing hotkey action
            if "key" in action_inputs:
                hotkey = action_inputs.get("key", "")
            else:
                hotkey = action_inputs.get("hotkey", "")

            if hotkey == "arrowleft":
                hotkey = "left"

            elif hotkey == "arrowright":
                hotkey = "right"

            elif hotkey == "arrowup":
                hotkey = "up"

            elif hotkey == "arrowdown":
                hotkey = "down"
            
            keys = hotkey.split(' ')
           
            converted_keys = []
            for key in keys:
                key_lower = key.lower()
                if key_lower in key_mapping:
                    converted_keys.append(key_mapping[key_lower])
                else:
                   
                    converted_keys.append(key_lower.capitalize())
            
           
            new_content = '+'.join(converted_keys)
            browsergym_actions.append(f"keyboard_press('{new_content}')")
        
        elif action_type == 'wait':
            browsergym_actions.append("wait(5000)")
        
        elif action_type == 'scroll':
            parser_results = ui_tars_scroll_to_browsergym(
                action_inputs=action_inputs,
                image_height=image_height,
                image_width=image_width, 
                magnitude=magnitude,
                click_before_scroll=click_before_scroll
            )
            for action in parser_results:
                browsergym_actions.append(action)
        
        elif action_type == 'finished':
            content = action_inputs.get("content", "")
            content = escape_single_quotes(content)
            browsergym_actions.append(f"send_msg_to_user('{content}')")
        
    return browsergym_actions


def parsing_response_to_android_format(
    responses, 
    image_height: int = ANDROID_HEIGHT,
    image_width: int = ANDROID_WIDTH
) -> list[str]:
    
    if isinstance(responses, dict):
        responses = [responses]
    
    android_actions = []
    for response in responses:
        action_dict = response
        action_type = action_dict.get("action_type")
        action_inputs = action_dict.get("action_inputs", {})
        
        if action_type in ['click', 'long_press']:
            # Parsing click actions
            start_box = action_inputs.get("start_box")
            start_box = str(start_box)
            
            if start_box:
                start_box = eval(start_box)
                if len(start_box) == 4:
                    x1, y1, x2, y2 = start_box  # Assuming box is in [x1, y1, x2, y2]
                elif len(start_box) == 2:
                    x1, y1 = start_box
                    x2 = x1
                    y2 = y1
                x = int(float((x1 + x2) / 2) * image_width)
                y = int(float((y1 + y2) / 2) * image_height)
                
                if action_type == 'click':
                    android_actions.append(json.dumps({'action_type': 'click', 'x': x, 'y': y}))
                elif action_type == 'long_press':
                    android_actions.append(json.dumps({'action_type': 'long_press', 'x': x, 'y': y}))
        
        elif action_type == 'drag':
            # Parsing drag action based on start and end_boxes
            start_box = action_inputs.get("start_box")
            end_box = action_inputs.get("end_box")
            if start_box and end_box:
                x1, y1, x2, y2 = eval(
                    start_box)  # Assuming box is in [x1, y1, x2, y2]
                sx = int(float((x1 + x2) / 2) * image_width)
                sy = int(float((y1 + y2) / 2) * image_height)
                x1, y1, x2, y2 = eval(
                    end_box)  # Assuming box is in [x1, y1, x2, y2]
                ex = int(float((x1 + x2) / 2) * image_width)
                ey = int(float((y1 + y2) / 2) * image_height)
                android_actions.append(json.dumps({'action_type': 'drag_and_drop', 'touch_xy': [sx, sy], 'lift_xy': [ex, ey]}))
        
        elif action_type == 'type':
            # Parsing typing action using clipboard
            content = action_inputs.get("content", "")
            content = escape_single_quotes(content)
            stripped_content = content
            if content.endswith("\n") or content.endswith("\\n"):
                stripped_content = stripped_content.rstrip("\\n").rstrip("\n")
            if content:
                android_actions.append(json.dumps({'action_type': 'input_text', 'text': stripped_content}))

        elif action_type == 'wait':
            android_actions.append(json.dumps({'action_type': 'wait'}))
        
        elif action_type == 'scroll':
            # Parsing scroll actions
            start_box = action_inputs.get("start_box", None)
            direction = action_inputs.get("direction", None)

            if direction is None:
                raise ValueError(f"Direction is required for scroll action. Action inputs: {action_inputs}")
            
            if start_box is None:
                direction = str(direction)
                android_actions.append(json.dumps({'action_type': 'scroll', 'direction': direction}))
            else:
                start_box = str(start_box)
            
                if start_box == '<point>x1 y1</point>' and direction:
                    android_actions.append(json.dumps({'action_type': 'scroll', 'direction': direction}))
                else:
                    start_box = eval(start_box)
                    if len(start_box) == 4:
                        x1, y1, x2, y2 = start_box  # Assuming box is in [x1, y1, x2, y2]
                    elif len(start_box) == 2:
                        x1, y1 = start_box
                        x2 = x1
                        y2 = y1
                    x = int(float((x1 + x2) / 2) * image_width)
                    y = int(float((y1 + y2) / 2) * image_height)
                    android_actions.append(json.dumps({'action_type': 'scroll', 'x': x, 'y': y, 'direction': direction}))

        elif action_type == 'finished':
            content = action_inputs.get("content", "")
            content = escape_single_quotes(content)
            android_actions.append(json.dumps({'action_type': 'answer', 'text': content}))
        
        elif action_type == 'open_app':
            app_name = action_inputs.get("app_name", "")
            app_name = str(app_name)
            if app_name:
                android_actions.append(json.dumps({'action_type': 'open_app', 'app_name': app_name}))
        
        elif action_type == 'press_home':
            android_actions.append(json.dumps({'action_type': 'navigate_home'}))
        
        elif action_type == 'press_back':
            android_actions.append(json.dumps({'action_type': 'navigate_back'}))

        else:
            print(f"\n# Unrecognized action type: {action_type}")
    
    return android_actions


def add_box_token(input_string):
    # Step 1: Split the string into individual actions
    if "Action: " in input_string and "start_box=" in input_string:
        suffix = input_string.split("Action: ")[0] + "Action: "
        actions = input_string.split("Action: ")[1:]
        processed_actions = []
        for action in actions:
            action = action.strip()
            # Step 2: Extract coordinates (start_box or end_box) using regex
            coordinates = re.findall(
                r"(start_box|end_box)='\((\d+),\s*(\d+)\)'", action)

            updated_action = action  # Start with the original action
            for coord_type, x, y in coordinates:
                # Convert x and y to integers
                updated_action = updated_action.replace(
                    f"{coord_type}='({x},{y})'",
                    f"{coord_type}='<|box_start|>({x},{y})<|box_end|>'")
            processed_actions.append(updated_action)

        # Step 5: Reconstruct the final string
        final_string = suffix + "\n\n".join(processed_actions)
    else:
        final_string = input_string
    return final_string
