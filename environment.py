#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import re
import json
import time
import yaml
import numpy as np
import random as rd

from PIL import Image
from typing import Any
from pathlib import Path

from core.logger import MyLogger
from core.data_model import Observation
from GUITestBench.constant import CONDITION
from GUITestBench.app_environment import AppEnvironmentManager

from android_world.agents import m3a_utils
from android_world.env.json_action import JSONAction
from android_world.agents.seeact_utils import format_and_filter_elements

MAX_OUTER_LOOPS = 20

def is_equivalent(action1: dict, action2: dict) -> bool:
    if action1['action_type'] != action2['action_type']:
        return False
    else:
        action_type = action1['action_type']
        match action_type:
            case 'answer':
                return action1['text'] == action2['text']
            case 'click':
                return action1['x'] == action2['x'] and action1['y'] == action2['y']
            case 'scroll':
                return action1['direction'] == action2['direction']
            case 'long_press':
                return action1['x'] == action2['x'] and action1['y'] == action2['y']
            case 'drag_and_drop':
                return action1['touch_xy'] == action2['touch_xy'] and action1['lift_xy'] == action2['lift_xy']
            case 'open_app':
                return action1['app_name'] == action2['app_name']
            case 'input_text':
                return action1['text'] == action2['text']
            case 'navigate_home':
                return True
            case 'navigate_back':
                return True
            case _:
                return False

class MobileAgentEnv:            
    def __init__(
        self, 
        task_name: str = None,
        config_path: str = None
    ):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # set environment config
        env_config = self.config.get('environment', {})
        self.use_set_of_marks = env_config.get('use_set_of_marks', True)
        self.console_port = env_config.get('console_port', 5556)
        self.grpc_port = env_config.get('grpc_port', 8557)
        self.adb_path = env_config.get('adb_path', 'your/path/to/adb')
        self.app_env_manager = AppEnvironmentManager(
            console_port=self.console_port,
            grpc_port=self.grpc_port,
            adb_path=self.adb_path
        )
        
        # set experiment counters
        self.k = 3
        self.loops = 0
        self.screenshot_id = 0

        # set experiment config
        exp_config = self.config.get('experiment', {})
        self.task_seed = exp_config.get('task_seed', 42)
        self._init_seed()
        
        self.task_name = task_name
        self.exp_root = exp_config.get('exp_root', './experiments')
        self._init_experiment()
        
        self.logname = exp_config.get('logname', 'guitest.log')
    
    def _init_seed(self) -> None:
        np.random.seed(self.task_seed)
        rd.seed(self.task_seed)
    
    def _init_experiment(self) -> None:
        exp_str = re.sub(r"[\/:*?<>|]", "_", self.task_name)
        
        for i in range(1000):
            if i >= 999:  # make sure we don't loop forever
                raise ValueError("Could not find a unique name for the experiment directory.")
            tag = f"_{i}" if i > 0 else ""
            self.exp_dir = Path(self.exp_root) / f"{exp_str}{tag}"
            if not self.exp_dir.exists():
                break
        
        self.exp_dir.mkdir(parents=True, exist_ok=True)
        self.state_storage_dir = self.exp_dir / "state_storage"         
        self.state_storage_dir.mkdir(parents=True, exist_ok=True)
        self.trace_storage_dir = self.exp_dir / "trace_storage.json"     
    
    def _init_app(self, app_name: str, db_data: Any = None) -> bool:
        success = self.app_env_manager.prepare_environment(
            app_name=app_name,
            db_data=db_data
        )
        
        if success:
            self.app_env_manager.open_app(app_name)
        else:
            print(f"⚠️ Failed to prepare environment for {app_name}")
        
        return success

    def _init_task(self, **kwargs) -> None:
        self.logger = MyLogger(log_dir=self.exp_dir)
        
        task_str = kwargs.get('task', None)
        if not task_str:
            raise ValueError('No task specified!')
        
        app_name = kwargs.get('app_name', None)
        if app_name: 
            db_data = CONDITION.get(app_name, None)
            self._init_app(app_name=app_name, db_data=db_data)
        
        model_name = kwargs.get('model_name', 'uitars')
        match model_name:
            case 'uitars':
                from GUIAgent.uitars import Executor_UITARS
                self.agent = Executor_UITARS(task=task_str, app_name=app_name)
            case 'uitars-7b':
                from GUIAgent.uitars import Executor_UITARS
                self.agent = Executor_UITARS(task=task_str, app_name=app_name)
            case 'uitars_1_5':
                from GUIAgent.uitars1_5 import Executor_UITARS_1_5
                self.agent = Executor_UITARS_1_5(task=task_str, app_name=app_name)
            case 'guiowl':
                pass
            case _:
                raise ValueError(f"Unknown model name: {model_name}")
            
        self.logger.record(
            name=self.logname, 
            content=f">>> {self.agent.name} has been initialized with task: {task_str}"
        )
        
    def get_observation(self) -> None:
        state = self.app_env_manager.get_state(wait_to_stabilize=True)
        time.sleep(1)
        screenshot_array = state.pixels
        if len(screenshot_array.shape) == 3:
            screenshot_image = Image.fromarray(screenshot_array).convert('RGB')
        else:
            screenshot_image = Image.fromarray(screenshot_array)
        
        image_dir = f"{self.state_storage_dir}/screenshot_{self.screenshot_id}.png"
        screenshot_image.save(image_dir)
        
        ui_elements = state.ui_elements
        if self.use_set_of_marks:
            try:
                params = self.app_env_manager.get_params()
                logical_screen_size = params.logical_screen_size
                physical_frame_boundary = params.physical_frame_boundary
                orientation = params.orientation

                # Convert PIL image back to numpy array for processing
                screenshot_array = np.array(screenshot_image)

                # Add UI element markers
                for index, ui_element in enumerate(ui_elements):
                    # Only add markers for visible UI elements
                    if m3a_utils.validate_ui_element(ui_element, logical_screen_size):
                        m3a_utils.add_ui_element_mark(
                            screenshot_array,
                            ui_element,
                            index,
                            logical_screen_size,
                            physical_frame_boundary,
                            orientation,
                        )
                # Convert back to PIL Image
                som_screenshot_image = Image.fromarray(screenshot_array.astype('uint8'))
                som_image_dir = f"{self.state_storage_dir}/som_screenshot_{self.screenshot_id}.png"
                som_screenshot_image.save(som_image_dir)
            
            except Exception as e:
                self.logger.record(
                    name=self.logname,
                    content=f"Warning: Could not add UI markers due to error: {e}"
                )
        
        self.screenshot_id += 1
        
        self.observation = Observation(
            url="",
            text_desc=format_and_filter_elements(ui_elements), 
            image_dir=image_dir
        )
    
    def save_trace(self) -> None:
        trace = self.agent.extract_steps()
        trace.append({'observation': self.observation.image_dir})
        with open(self.trace_storage_dir, 'w', encoding='utf-8') as file:
            json.dump(trace, file, ensure_ascii=False, indent=4)
    
    def early_stop(self) -> bool:
        trace = self.agent.extract_steps()
        
        action_chain = [step['action']['actions'][0] for step in trace if step['types'] == 'Executor']
        last_k_actions = action_chain[-self.k:]
        last_action = action_chain[-1]
        if len(last_k_actions) >= self.k:
            if all(
                [is_equivalent(last_action, action) for action in last_k_actions]
            ):
                self.logger.record(name=self.logname, content=f"⚠️ Same action for {self.k} times")
                return True
        
        return False
    
    def is_navigate_home(self, action: JSONAction) -> bool:
        return action.action_type == 'navigate_home'
    
    def run(self):
        terminated = False
        
        try:
            self.get_observation()
            
            while not terminated:
                self.loops += 1
                if self.loops > MAX_OUTER_LOOPS:
                    self.logger.record(
                        name=self.logname, 
                        content=f"⚠️ Max loops {MAX_OUTER_LOOPS}, task exit!"
                    )
                    break
                
                android_format_action = self.agent.call(observation=self.observation)
                
                if not android_format_action:
                    self.logger.record(name=self.logname, content="❌ [Error] No action, task exit!")
                    break
                
                for action_str in android_format_action:
                    
                    if action_str == 'NOOP':
                        self.logger.record(
                            name=self.agent.logname, 
                            content=" ------ Task finished with NOOP ------ "
                        )
                        terminated = True
                        break
                   
                    early_stop_flag = self.early_stop()
                    if early_stop_flag:
                        terminated = True
                        break                    
                    
                    self.logger.record(name=self.logname, content=action_str)
                    action_dict = json.loads(action_str)
                    action = JSONAction(**action_dict)
                    
                    # Check navigate_home action
                    if self.is_navigate_home(action):
                        self.logger.record(name=self.logname, content="⚠️ Navigate home action detected")
                        terminated = True
                        break
                    
                    try:
                        self.app_env_manager.execute_adb_action(
                            action, self.observation
                        )
                    except Exception as e:
                        self.logger.record(name=self.logname, content=f"❌ [Error] env.step error: {e}, task exit!")
                        terminated = True
                        break
                    
                    self.get_observation()

        finally:
            self.save_trace()
            self.app_env_manager.close()
