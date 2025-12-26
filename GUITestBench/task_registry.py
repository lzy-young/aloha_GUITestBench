#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import json

from utils.fileio import load
from dataclasses import dataclass

@dataclass
class TaskConfig:
    task: str = "" 
    task_id: int = 0
    app_name: str = ""
    app_cate: str = ""
    defect_id: str = ""
    defect_cate: str = ""
    defect_type: str = ""
    defect_desc: str = ""
    reproduce_step: int = ""
    
    def to_dict(self) -> dict:
        return {
            'task': self.task,
            'task_id': self.task_id,
            'app_name': self.app_name,
            'app_cate': self.app_cate,
            'defect_cate': self.defect_cate,
            'defect_id': self.defect_id,
            'defect_type': self.defect_type,
            'defect_desc': self.defect_desc, 
            'reproduce_step': self.reproduce_step
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TaskConfig':
        return cls(
            task=data['task'],
            task_id=data['task_id'],
            app_name=data['app_name'],
            app_cate=data['app_cate'],
            defect_id=data['defect_id'],
            defect_cate=data['defect_cate'],
            defect_type=data['defect_type'],
            defect_desc=data['defect_desc'], 
            reproduce_step=data['reproduce_step']
        )

if __name__ == "__main__":
    total_data = load('./GUITestBench/gui_test_bench.json')
    
    index = 0
    for data in total_data:
        instructions = data['instructions']
        defects_oriented = instructions['defects_oriented']
        exploration_oriented = instructions['exploration_oriented']
        instructions = defects_oriented + exploration_oriented
        
        for ins in instructions:
            task=TaskConfig(
                task=ins, 
                task_id=index, 
                app_name=data['app_name'], 
                app_cate=data['app_info']['app_cate'],
                defect_id=data['defect_id'], 
                default_cate=data['default_cate'],
                defect_type=data['defect_type'], 
                defect_desc=data['defect_info']['defect_desc'], 
                reproduce_step=data['defect_info']['reproduce_step']
            )
            task_dict = task.to_dict()
            with open(f'./GUITester/config_files/{task.task_id}.json', 'w') as f:
                json.dump(task_dict, f, indent=4)
            index += 1
