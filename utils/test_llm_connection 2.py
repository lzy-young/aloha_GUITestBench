import requests
from utils.fileio import load

model_configs = load('./configs/model.json')
def test_llm_connection(model_name, sys_msg='', user_msg=''):
    if model_name not in model_configs:
        raise ValueError(f'Model {model_name} is not defined in ./configs/model.json')
    model_config = model_configs[model_name]
    print(f'Testing {model_name}. Endpoint: {model_config["endpoint"]}')
    res = requests.post(model_config['endpoint'],
                        headers=model_config['headers'],
                        json={
                            "model_name": model_config['model_name'],
                            "messages": [
                                {"role": "system", "content": sys_msg},
                                {"role": "user", "content": user_msg}
                            ],
                            "stream": False
                        })
    res.raise_for_status()
    print(res.content)


if __name__ == '__main__':
    test_llm_connection('qwen72b')
