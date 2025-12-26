import os
import argparse

from utils.fileio import load
from environment import MobileAgentEnv
from GUITestBench.task_registry import TaskConfig


def check_exist(llm, task_name):
    return os.path.exists(f"experiments-{llm}/{task_name}")

if __name__ == '__main__':
    
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--llm', type=str, default='uitars')
    argparser.add_argument('--config_files', type=str, default='./configs/task')
    argparser.add_argument('--test_start_idx', type=int, default=0, help='start index of the task')
    argparser.add_argument('--test_end_idx', type=int, default=100, help='end index of the task')
    args = argparser.parse_args()
    
    test_file_list = []
    st_idx = args.test_start_idx
    ed_idx = args.test_end_idx
    for i in range(st_idx, ed_idx):
        test_file_list.append(os.path.join(args.config_files, f'{i}.json'))
    
    for config_files in test_file_list:
        config = load(config_files)
        task_config = TaskConfig(**config)
        task_name = '_'.join([task_config.defect_id, args.llm, str(task_config.task_id)])
        
        if check_exist(args.llm, task_name):
            continue
        
        print('='*100)
        print(f"⚙️ [Executor]: {args.llm}")
        print(f"🔢 [Defect Id]: {task_config.defect_id}")
        print(f"❌ [Defect Type]: {task_config.defect_type}")
        print(f"🔥 [Eval Task]: {task_config.task}")
        print(f"📝 [Task Name]: {task_name}")
        print('='*100)
        
        try:
            env = MobileAgentEnv(
                task_name=task_name,
                config_path='./configs/android_env.yaml'
            )
            env._init_task(**{
                'task': task_config.task,
                'model_name': args.llm,
                'app_name': task_config.app_name,
            })
            env.run()
        except:
            continue