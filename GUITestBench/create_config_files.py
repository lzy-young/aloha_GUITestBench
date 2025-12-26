import os
import json
import numpy as np
import pandas as pd

df = pd.read_excel('./GUITestBench/data.xlsx')
data = df.to_dict(orient='records')

saving_data = []
for item in data:
    defects_tasks, exploration_tasks = [], []
    
    target_file = f"./GUITestBench/defects_oriented/{item['defect_id']}.json"
    if os.path.exists(target_file):
        with open(target_file, 'r') as file:
            defects_tasks = json.load(file)
    else:
        continue
    
    target_file = f"./GUITestBench/exploration_oriented/{item['defect_id']}.json"
    if os.path.exists(target_file):
        with open(target_file, 'r') as file:
            exploration_tasks = json.load(file)
    else:
        continue
    
    tasks = {
        'defects_oriented': defects_tasks, 
        'exploration_oriented': exploration_tasks
    }
    
    new_item = {
        'defect_id': item['defect_id'], 
        'app_name': item['app_name'], 
        'defect_cate': item['defect_cate'], 
        'defect_type': item['defect_type'], 
        'defect_desc': item['defect_desc'], 
        'instructions': tasks, 
        'defect_info': {
            'github_link': item['github_link'], 
            'reproduce_step': item['steps'], 
        }, 
        'app_info': {
            'apk_name':  item['apk_name'], 
            'apk_version':  item['apk_version'], 
            'activity': item['activity'], 
            'app_desc': item['app_desc'], 
            'app_cate': item['app_cate']
        }, 
        'eval': {
            'judge_method': item['judge_method'], 
            'observation': item['observation'], 
            'action_type': item['action_type'], 
            'bbox': eval(item['bbox']), 
            'text': None if item['text'] is np.nan else item['text'], 
            'direction': None,
            'add_info': None if item['add_info'] is np.nan else item['add_info'], 
        }
    }
    
    saving_data.append(new_item)

with open('./GUITestBench/gui_test_bench.json', 'w', encoding='utf-8') as file:
    json.dump(saving_data, file, ensure_ascii=False, indent=4)


target_folder = './config_files'
os.makedirs(target_folder, exist_ok=True)

index = 0
for _, item in enumerate(saving_data):
    ins_list = item['instructions']['defects_oriented'] + item['instructions']['exploration_oriented']
    for ins in ins_list:
        new_item = {
            'task': ins, 
            'task_id': index, 
            'app_name': item['app_name'], 
            'app_cate': item['app_info']['app_cate'], 
            'defect_cate': item['defect_cate'], 
            'defect_id': item['defect_id'], 
            'defect_type': item['defect_type'], 
            'defect_desc': item['defect_desc'], 
            'reproduce_step': item['defect_info']['reproduce_step']
        }
        with open(os.path.join(target_folder, f"{index}.json"), 'w') as file:
            json.dump(new_item, file, indent=4)
        index += 1
