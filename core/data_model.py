from enum import Enum
from pydantic import BaseModel
from typing import Union, Any, Optional

# region data model
class Action(BaseModel):
    raw_action: list[str] = []         
    actions: list[str] = []             

class OTA(BaseModel):
    observation: str = ""               # Observation.image_dir
    thought: str = ""                   # Action.thought
    action: Action = None               # Action.actions

class Observation(BaseModel):
    url: str = ""                               # url
    text_desc: Any                              
    image_dir: Union[str, None] = None          # screenshot dir
    
class Reflection(BaseModel):
    thinking: str = ""
    root_cause: str = ""
    failure_mode: str = ""
    action: str = ""
    detail: str = ""

class Plan(BaseModel):
    name: str = ""
    info: str = ""
    expectation: str = ""
    possible_flaws: list[str] = []

class PlanInfo(BaseModel):
    thinking: str = ""
    remaining_list: list[Plan] = []
    completed_list: list[Plan] = []
    failed_list: list[Plan] = []

# Task Progress Recording Node
class TPNode(BaseModel):
    name: str = ""
    info: str = ""
    status: str = ""

# Defect Ground Truth
class Defect(BaseModel):
    app_desc: Optional[str] = None                   
    judge_method: Optional[str] = None              
    defect_id: Optional[str] = None                  
    defect_type: Optional[str] = None                
    observation: Optional[str] = None                
    action_type: Optional[str] = None                
    bbox: Optional[list] = None                     
    text: Optional[str] = None                       
    direction: Optional[str] = None                  
    add_info: Optional[str] = None                   
    
class EventType(str, Enum):
    GUI_BUG = "GUI_BUG"                  
    EXECUTOR_ERROR = "EXECUTOR_ERROR"    

class Event(BaseModel):
    event_type: EventType                           
    trajectory_segment: list[dict]                  
    is_arrived: Optional[bool] = None               
    actual_type: Optional[EventType] = None         
    matched_defect_id: Optional[str] = None         
    
    def to_dict(self):
        return {
            "event_type": self.event_type.value,
            "trajectory_segment": self.trajectory_segment,
            "is_arrived": self.is_arrived,
            "actual_type": self.actual_type.value if self.actual_type else None,
            "matched_defect_id": self.matched_defect_id
        }

class EnvParams(BaseModel):
    logical_screen_size: tuple
    physical_frame_boundary: tuple
    orientation: int