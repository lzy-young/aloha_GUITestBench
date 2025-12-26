import os
import time
from copy import deepcopy
from typing import Union, Literal, Optional

import requests
from langchain_core.messages import HumanMessage

from core.logger import MyLogger
from core.models.MyBedrockLLM import MyBedrockLLM
from core.models.MyClaudeLLM import MyClaudeLLM
from core.models.MyOpenAILLM import MyOpenAILLM
from core.models.MyBaseLLM import MyBaseLLM
from core.models.MyQwenLLM import MyQwenLLM
from utils.fileio import load, save
from utils.live_file import LiveJsonFile


def type2role(msg_type: str) -> str:
    return {
        "human": "user",
        "ai": "assistant",
        "system": "system"
    }[msg_type]


model_config = LiveJsonFile('configs/model.json')

supported_cot_models = [model_name for model_name in model_config if 'cot' in model_config[model_name]['type']]
SupportedCOTModel = Literal[tuple(supported_cot_models)]
print('Supported COT Models: ', supported_cot_models)

supported_text_models = [model_name for model_name in model_config if 'text' in model_config[model_name]['type']]
SupportedTextModel = Literal[tuple(supported_text_models)]
print('Supported Text Models: ', supported_text_models)

supported_vl_models = [model_name for model_name in model_config if 'vl' in model_config[model_name]['type']]
SupportedVLModel = Literal[tuple(supported_vl_models)]
print('Supported VL Models: ', supported_vl_models)

SupportedModel = Union[SupportedTextModel, SupportedCOTModel, SupportedVLModel]
default_models = LiveJsonFile('./configs/default_models.json')


def fetch_arsenal_token(arsenal_token_provider: str, proxies: Optional[dict] = None) -> str:
    res = requests.post(
        arsenal_token_provider,
        headers={
            "Content-Type": "application/json",
        },
        json={
            "app_id": "1d40b6b529c6422bbd1abed246d4c327",
            "app_secret": "IOZ3NYptqxCWGV1OG/qrZ17Fv8yA7fBHlkMvLad5iEE=",
        },
        proxies=proxies     
    )
    token = res.json()['data']['token']
    print('Get New Token: ', token)
    return token


def get_arsenal_token(arsenal_token_provider: str, proxies: Optional[dict] = None) -> str:
    token_path = './core/static/token.json'
    if os.path.isfile(token_path):
        cache = load(token_path)
        if cache['create_time'] + 6 * 24 * 60 * 60 > time.time():
            return cache['token']
    token = fetch_arsenal_token(arsenal_token_provider, proxies=proxies)
    save(token_path, {
        'create_time': time.time(),
        'token': token
    })
    return token


def model_factory(model, sys_msg: Union[str, list[str]],
                  params: Optional[dict] = None,
                  tools: list = None,
                  logger: MyLogger = None) -> MyBaseLLM:
    if tools is None:
        tools = []
    if params is None:
        params = {}
    config = deepcopy(model_config[model])
    proxies = None
    if 'proxies' in config:
        proxies = config['proxies']
        del config['proxies']
    if 'connect_arsenal' in config:
        config['headers']['token'] = get_arsenal_token(config['connect_arsenal'], proxies=proxies)
        del config['connect_arsenal']
    model_type = 'default'
    if 'api_type' in config:
        model_type = config['api_type']
        del config['api_type']
    config['params'] = {
        **config['params'],
        **params,
    }

    if model_type == 'claude':
        llm_type = MyClaudeLLM
    elif model_type == 'bedrock':
        llm_type = MyBedrockLLM
    elif model_type == 'qwen3':
        llm_type = MyQwenLLM
    else:
        llm_type = MyOpenAILLM

    llm = llm_type(
        **config,
        sys_msg=sys_msg,
        proxies=proxies,
        logger=logger,
    )
    if len(tools) > 0:
        llm = llm.bind_tools(tools=tools)
    return llm


def test_model(model, msg: str) -> None:
    model = model_factory(model, '')
    for res in model.stream([HumanMessage(content=[{"type": "text", "text": msg}])]):
        print(res.content, end='')
    print()
