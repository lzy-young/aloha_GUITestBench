import os
import json
import yaml

from pydantic import BaseModel
from core.data_model import Observation, Action
from core.MyAgent import MyAgent, Request, LLMConfig
from core.utils.get_screenshot import screenshot_post_process_v2
from utils.re_func import extract_ins_content, extract_action_content
from utils.ui_tars_action_parser import (
    parse_action_to_structure_output, 
    parsing_response_to_android_format
)

prompt_wrap = """You are a GUI Agent with defect detection capabilities. While completing the navigation task, you need to examine each interface from the perspective of a "test engineer":
- Before and after each execution: Consider whether the model's response matches expectations.
- Throughout: Pay attention to anything that seems "off".

**Bug Reporting Requirements**:
- When you find a potential defect, output it as finished(content='GUI_BUG').
- Do not interrupt the main task because of finding a defect.
- If the defect is obvious, output it as finished(content='').

The name of current app is {app_name}. Here is the navigation task: {task_instruction}"""


class Step(BaseModel):
    thought: str = ""
    action: Action = None
    observation: str = ""


class Executor_UITARS(MyAgent):
    name = "UI-TARS"
    
    def __init__(self, task: str, app_name: str, config_path: str = './configs/setup_uitars.yaml') -> None:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        worker_config = config.get('worker', {})
        parser_config = config.get('parser', {})
        self.worker_sys_prompt = worker_config.get('sys_prompt', 'prompt-uitars-system.md')
        self.parser_sys_prompt = parser_config.get('sys_prompt', 'prompt-parser-system.md')
        self.parser_user_prompt = parser_config.get('user_prompt', 'prompt-parser-user.md')
        self.use_set_of_marks = config.get('use_set_of_marks', False)
        self.original_image_width = config.get('original_image_width', 1080)
        self.original_image_height = config.get('original_image_height', 2400)

        super().__init__(
            log_key=self.name,
            llms={
                "worker": LLMConfig(
                    name=worker_config.get('llms', 'ui-tars-70b'), 
                    sys_prompt=self._load_prompt(self.worker_sys_prompt), 
                    params={
                        "temperature": worker_config.get('temperature', 0.1), 
                        "max_tokens": worker_config.get('max_tokens', 4096)
                    }
                ), 
                'action_parser': LLMConfig(
                    name=parser_config.get('llms', 'gpt-4o'), 
                    sys_prompt=self._load_prompt(self.parser_sys_prompt),
                    params={
                        "temperature": parser_config.get('temperature', 1.0), 
                        "max_tokens": parser_config.get('max_tokens', 2048)
                    }
                )
            }, 
            lang='en-us'
        )

        self.task: str = task
        self.app_name: str = app_name
        self.trace: list[Step] = []
    
    
    def extract_steps(self) -> list:
        data = []
        for step in self.trace:
            data.append({
                'types': 'Executor', 
                'observation': step.observation, 
                'thought': step.thought, 
                'action': {
                    'raw_action': step.action.raw_action,                           # UI-TARS action
                    'actions': [json.loads(act) for act in step.action.actions]     # Android supported action
                }
            })
        return data
    
    
    def update_state(self, new_observation: Observation):
        self.global_state = new_observation
        if self.use_set_of_marks:
            screenshot_name = new_observation.image_dir.split('/')[-1]
            som_screenshot_name = "som_" + screenshot_name
            som_image_dir = new_observation.image_dir.replace(
                screenshot_name, som_screenshot_name
            )
            if os.path.exists(som_image_dir):
                self.global_state.image_dir = som_image_dir
            else:
                self.global_state.image_dir = new_observation.image_dir
        print("执行器更新全局状态:", self.global_state.image_dir)

    
    def wrap_assistant_steps(self) -> list[str]:
        historical_steps = []
        for step in self.trace:
            action_str = ", ".join(step.action.raw_action)
            historical_steps.append(f"Thought: {step.thought}\nAction: {action_str}")
        return historical_steps
    
    
    def wrap_instruction(self) -> list[str]:
        task_str = prompt_wrap.format(app_name=self.app_name, task_instruction=self.task)
        task_str = f"\n\n## User Instruction\n{task_str}"
        return [task_str]
    
    def action_check(self, action: str) -> list[str]:
        prompt = self._load_prompt(
            name=self.parser_user_prompt, 
            params={"action": action}
        )
        req = Request(llm='action_parser', prompt=prompt, screenshot=[])
        res = self.query(req, suffix='gui-parse')
        raw_action = "".join(stream_cache.chunk for stream_cache in res)
        action = extract_ins_content(raw_action)
        return action
    
    def action_replace(
        self, 
        raw_action: str, 
        target_action: str,
        correct_action: list[str]
    ) -> str:
        correct_action_str = ", ".join(correct_action)
        return raw_action.replace(target_action, correct_action_str)
    
    def construct_request(self) -> Request:
        prompt = {
            'user': self.wrap_instruction(),            
            'assistant': self.wrap_assistant_steps()    
        }
        return Request(
            llm="worker", 
            prompt=prompt, 
            screenshot=[screenshot_post_process_v2(self.global_state.image_dir)]
        )
    
    def parse_response(self, raw_response: str) -> list[str]:
        
        
        action_content = extract_action_content(raw_response)
        action_content_checked = self.action_check(action_content)
        raw_action = self.action_replace(
            raw_action=raw_response, 
            target_action=action_content,
            correct_action=action_content_checked
        )
        
        try:
            
            parsed_dict = parse_action_to_structure_output(
                raw_action,
                factor=1000,
                origin_resized_height=self.original_image_height,
                origin_resized_width=self.original_image_width,
                model_type="qwen2vl"
            )

            
            android_format_action = parsing_response_to_android_format(
                parsed_dict, 
                image_height=self.original_image_height,
                image_width=self.original_image_width
            )

            
            thought = parsed_dict[0].get('thought', '')
            reflection = parsed_dict[0].get('reflection', '')
            thinking = (
                f"{thought}\n{reflection}" if thought and reflection else
                thought if thought else
                reflection
            )
        except:
            thinking = ''
            action_content_checked = []
            android_format_action = []

        
        action_step = Step(
            thought=thinking,
            action=Action(
                raw_action=action_content_checked,
                actions=android_format_action
            ), 
            observation=self.global_state.image_dir
        )
        self.trace.append(action_step)
        
        return android_format_action
    
    def call(self, observation: Observation) -> list[str]:
        self.update_state(observation)      
        req = self.construct_request()
        res = self.query(req, suffix=self.name)
        raw_response = "".join(stream_cache.chunk for stream_cache in res)    
        return self.parse_response(raw_response)
