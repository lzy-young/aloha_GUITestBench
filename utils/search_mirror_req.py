import os
import traceback
from typing import Any

from utils.fileio import load


def search_mirror_req(code_id: str = None, type: str = None, attr: dict[str, Any] = None) -> None:
    req_folder = 'logs/requests'
    for req in sorted(os.listdir(req_folder)):
        req_path = os.path.join(req_folder, req, 'full_payload.json')
        mir_path = os.path.join(req_folder, req, 'full_mirror.json')

        try:
            payload = load(req_path)
            mirror = load(mir_path)

            if code_id is not None and payload['uuid'] != code_id:
                continue
            if type is not None and mirror['type'] != type:
                continue
            if attr is not None and any(key not in mirror or mirror[key] != attr[key] for key in attr):
                continue

            print(req)
        except:
            print(f'Failed to process: {req}.')
            print(traceback.format_exc())

