
import os
import datetime
import shutil
import traceback


def collect_logs(logs_path='./logs', days=3):
    print(f'Searching logs in {os.path.abspath(logs_path)}')

    paths = []
    for sub in os.listdir(logs_path):
        for log in os.listdir(os.path.join(logs_path, sub)):
            if not log[:8].isdigit():
                continue
            log_date = datetime.datetime(int(log[:4]), int(log[4:6]), int(log[6:8]))
            cur_date = datetime.datetime.now()
            interval = cur_date - log_date
            if interval.days > days:
                path = os.path.join(logs_path, sub, log)
                paths.append(path)
                print(f'Log to delete: {path}')

    return paths


def clean_logs(logs_path='./logs', days=3):
    paths = collect_logs(logs_path, days)

    r = input('Confirm deletion? (Y/n)').strip().lower()
    if r in ['n', 'no']:
        print('Canceled.')
        return
    for path in paths:
        print(f'Start to delete {path}')
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception:
            print(f'Failed to delete {path} because\n', traceback.format_exc())
