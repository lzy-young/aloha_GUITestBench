# Copyright 2025 The android_world Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Represents an action for Android interaction, parsed from a JSON format."""

import dataclasses
import json
from typing import Any, Optional


_JSON_SEPARATORS = (',', ':')

ANSWER = 'answer'
CLICK = 'click'
DOUBLE_TAP = 'double_tap'
INPUT_TEXT = 'input_text'
KEYBOARD_ENTER = 'keyboard_enter'
LONG_PRESS = 'long_press'
NAVIGATE_BACK = 'navigate_back'
NAVIGATE_HOME = 'navigate_home'
OPEN_APP = 'open_app'
SCROLL = 'scroll'
STATUS = 'status'
SWIPE = 'swipe'
UNKNOWN = 'unknown'
WAIT = 'wait'
DRAG_AND_DROP = 'drag_and_drop'    # 我的新增

_ACTION_TYPES = (
    CLICK,
    DOUBLE_TAP,
    SCROLL,
    SWIPE,
    INPUT_TEXT,
    NAVIGATE_HOME,
    NAVIGATE_BACK,
    KEYBOARD_ENTER,
    OPEN_APP,
    STATUS,
    WAIT,
    LONG_PRESS,
    ANSWER,
    UNKNOWN,
    DRAG_AND_DROP
)

UI_TARS_ACTION = (
    CLICK,             # click(point='<point>x1 y1</point>')
    LONG_PRESS,        # long_press(point='<point>x1 y1</point>')
    INPUT_TEXT,        # type(content='') #If you want to submit your input, use "\\n" at the end of `content`.
    SCROLL,            # scroll(point='<point>x1 y1</point>', direction='down or up or right or left')
    OPEN_APP,          # open_app(app_name=\'\')
    DRAG_AND_DROP,     # drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
    NAVIGATE_HOME,     # press_home()
    NAVIGATE_BACK,     # press_back()
    WAIT,              # wait() #Sleep for 5s and take a screenshot to check for any changes.
    ANSWER             # finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.
)

GUI_OWL_ACTION = (
    CLICK,             # {"name": "mobile_use", "arguments": {"action": "click", "coordinate": [x,y]}}
    LONG_PRESS,        # {"name": "mobile_use", "arguments": {"action": "long_press", "coordinate": [x,y], "time": 2.0}}
    INPUT_TEXT,        # {"name": "mobile_use", "arguments": {"action": "type", "text": content}}
    SCROLL,            # 
    OPEN_APP, 
    NAVIGATE_HOME,     # {"name": "mobile_use", "arguments": {"action": "system_button", "button": "Home"}}
    NAVIGATE_BACK,     # {"name": "mobile_use", "arguments": {"action": "system_button", "button": "Back"}}
    WAIT,              # {"name": "mobile_use", "arguments": {"action": "wait", "time": 3}}
    STATUS,            
    ANSWER,            # {"name": "mobile_use", "arguments": {"action": "answer", "text": content}}  
    KEYBOARD_ENTER,    # {"name": "mobile_use", "arguments": {"action": "system_button", "button": "Enter"}}
    UNKNOWN
)


_SCROLL_DIRECTIONS = ('left', 'right', 'down', 'up')

# Keys of JSON action.
ACTION_TYPE = 'action_type'
INDEX = 'index'
X = 'x'
Y = 'y'
TOUCH_XY = 'touch_xy'
LIFT_XY = 'lift_xy'
TEXT = 'text'
DIRECTION = 'direction'
APP_NAME = 'app_name'
GOAL_STATUS = 'goal_status'


ACTION_KEYS = [
    ACTION_TYPE,
    INDEX,
    X,
    Y,
    TOUCH_XY,
    LIFT_XY,
    TEXT,
    DIRECTION,
    APP_NAME,
    GOAL_STATUS,
]


@dataclasses.dataclass()
class JSONAction:
  """Represents a parsed JSON action.

  # Example
  result_json = {'action_type': 'click', 'x': %d, 'y': %d}
  action = JSONAction(**result_json)

  Attributes:
    action_type: The action type.
    index: The index to click, if action is a click. Either an index or a <x, y>
      should be provided. See x, y attributes below.
    x: The x position to click, if the action is a click.
    y: The y position to click, if the action is a click.
    text: The text to type, if action is type.
    direction: The direction to scroll, if action is scroll.
    goal_status: If the status is a 'status' type, indicates the status of the
      goal.
    app_name: The app name to launch, if the action type is 'open_app'.
    keycode: Keycode actions are necessary for an agent to interact with complex
      UI elements (like large textareas) that can't be accessed or controlled by
      simply taping, ensuring precise control over navigation and selection in
      the interface.
    clear_text: Whether to clear the text field before typing.
  """

  action_type: Optional[str] = None
  index: Optional[str | int] = None
  x: Optional[int] = None
  y: Optional[int] = None
  touch_xy: Optional[list[int]] = None
  lift_xy: Optional[list[int]] = None
  text: Optional[str] = None
  direction: Optional[str] = None
  goal_status: Optional[str] = None
  app_name: Optional[str] = None
  keycode: Optional[str] = None
  clear_text: Optional[bool] = None

  def __post_init__(self):
    if self.action_type not in _ACTION_TYPES:
      raise ValueError(f'Invalid action type: {self.action_type}')
    if self.index is not None:
      self.index = int(self.index)
      if self.x is not None or self.y is not None:
        raise ValueError('Either an index or a <x, y> should be provided.')
    if self.direction and self.direction not in _SCROLL_DIRECTIONS:
      raise ValueError(f'Invalid scroll direction: {self.direction}')
    if self.text is not None and not isinstance(self.text, str):
      self.text = str(self.text)
    if self.keycode is not None and not self.keycode.startswith('KEYCODE_'):
      raise ValueError(f'Invalid keycode: {self.keycode}')

  def __repr__(self) -> str:
    properties = []
    for key, value in self.as_dict(skip_none=True).items():
      if isinstance(value, float):
        value = f'{value:.3f}'
      properties.append(f'{key}={value!r}')
    return f"JSONAction({', '.join(properties)})"

  def __eq__(self, other):
    if isinstance(other, JSONAction):
      return _compare_actions(self, other)
    return False

  def __ne__(self, other):
    return not self.__eq__(other)

  def as_dict(self, skip_none: bool = True) -> dict[str, Any]:
    """Returns a dict representation of the action.

    Args:
      skip_none: Whether to skip none values.
    Returns:
      A dict representation of the action.
    """
    non_null = {}
    for key, value in self.__dict__.items():
      if value is not None:
        if skip_none and value is None:
          continue
        non_null[key] = value
    return non_null

  def json_str(self) -> str:
    non_null = self.as_dict(skip_none=True)
    return json.dumps(non_null, separators=_JSON_SEPARATORS)


def _compare_actions(a: JSONAction, b: JSONAction) -> bool:
  """Compares two JSONActions.

  Args:
    a: The first action.
    b: The second action.

  Returns:
    If the actions are equal.
  """
  # Ignore cases.
  if a.app_name is not None and b.app_name is not None:
    app_name_match = a.app_name.lower() == b.app_name.lower()
  else:
    app_name_match = a.app_name == b.app_name

  if a.text is not None and b.text is not None:
    text_match = a.text.lower() == b.text.lower()
  else:
    text_match = a.text == b.text

  # Compare the non-metadata fields.
  return (
      app_name_match
      and text_match
      and a.action_type == b.action_type
      and a.index == b.index
      and a.x == b.x
      and a.y == b.y
      and a.touch_xy == b.touch_xy
      and a.lift_xy == b.lift_xy
      and a.keycode == b.keycode
      and a.direction == b.direction
      and a.goal_status == b.goal_status
  )
