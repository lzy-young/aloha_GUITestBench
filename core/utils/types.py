from typing import List, Union, Any, Literal, Tuple, Dict, Optional, Generator

from pydantic import BaseModel

# region action
Pos = tuple[int, int]


class ClickAction(BaseModel):
    type: Literal['click'] = 'click'
    pos: Pos


class DoubleClickAction(BaseModel):
    type: Literal['double_click'] = 'double_click'
    pos: Pos


class RightClickAction(BaseModel):
    type: Literal['right_click'] = 'right_click'
    pos: Pos


class DragAction(BaseModel):
    type: Literal['drag'] = 'drag'
    start_pos: Pos
    end_pos: Pos


class PressAction(BaseModel):
    type: Literal['press'] = 'press'
    pos: Pos
    milliseconds: int


class MoveAction(BaseModel):
    type: Literal['move'] = 'move'
    pos: Pos


class HotkeyAction(BaseModel):
    type: Literal['hotkey'] = 'hotkey'
    hotkey: str


class TypeAction(BaseModel):
    type: Literal['type'] = 'type'
    content: str


class ScrollAction(BaseModel):
    type: Literal['scroll'] = 'scroll'
    direction: Literal['up', 'down', 'left', 'right']


class WaitAction(BaseModel):
    type: Literal['wait'] = 'wait'
    milliseconds: int


class FinishedAction(BaseModel):
    type: Literal['finished'] = 'finished'
    success: bool
    reason: str


Action = Union[
    ClickAction,
    DoubleClickAction,
    RightClickAction,
    DragAction,
    PressAction,
    MoveAction,
    HotkeyAction,
    TypeAction,
    ScrollAction,
    WaitAction,
    FinishedAction,
]


class AIActionStep(BaseModel):
    thoughts: str
    actions: list[Action]
    screenshot: str


class AIActionQuest(BaseModel):
    action: str
    # None for not check
    whether_performed: Union[str, None] = ''
    max_steps: int = 5

AIActionResponse = Generator[AIActionStep, None, None]


# endregion


# region query
class QueryWithFormat(BaseModel):
    query: str
    format: Optional[str] = None

AIQueryQuest = Union[str, QueryWithFormat]

class AIQueryResponse(BaseModel):
    thoughts: str
    response: str
    screenshot: str
# endregion


# region assert
class AIAssertionJudgement(BaseModel):
    thoughts: str
    passed: bool
    screenshot: str


AIAssertQuest = str
AIAssertResponse = AIAssertionJudgement


# endregion


# region wait
class AIWaitCondition(BaseModel):
    condition: AIAssertQuest
    max_milliseconds: int
    check_interval_milliseconds: int


AIWaitQuest = Union[int, AIAssertQuest, AIWaitCondition]
AIWaitResponse = tuple[AIAssertResponse, int]


# endregion


# region flow
class ActionStep(BaseModel):
    type: Literal['action'] = 'action'
    action: AIActionQuest


class ActionStepResponse(BaseModel):
    type: Literal['action'] = 'action'
    response: AIActionResponse


class QueryStep(BaseModel):
    type: Literal['query'] = 'query'
    query: AIQueryQuest


class QueryStepResponse(BaseModel):
    type: Literal['query'] = 'query'
    response: AIQueryResponse


class AssertStep(BaseModel):
    type: Literal['assert'] = 'assert'
    assertion: AIAssertQuest


class AssertStepResponse(BaseModel):
    type: Literal['assert'] = 'assert'
    response: AIAssertResponse


class WaitingStep(BaseModel):
    type: Literal['wait'] = 'wait'
    wait: AIWaitQuest


class WaitingStepResponse(BaseModel):
    type: Literal['wait'] = 'wait'
    response: AIWaitResponse


FlowStep = Union[
    ActionStep,
    QueryStep,
    AssertStep,
    WaitingStep,
]
Flow = list[FlowStep]

FlowStepResponse = Union[
    ActionStepResponse,
    QueryStepResponse,
    AssertStepResponse,
    WaitingStepResponse,
]
FlowResponse = Generator[FlowStepResponse, None, None]
# endregion
