import inspect
import os
import re
import time
import traceback
import uuid
from PIL import Image
from pathlib import Path
from typing import Union, Optional, Generator, Any

import requests.exceptions
from langchain_core.messages import HumanMessage, BaseMessage, AIMessage
from langchain_core.output_parsers.json import parse_partial_json
from langchain_core.utils.json import parse_json_markdown
from pydantic import BaseModel
from requests.exceptions import RetryError, HTTPError

from api.NonBlockingStreamingResponse import ResponseManager
from api.types import Code
from core.logger import MyLogger
from core.model import model_factory
from core.models.MyBaseLLM import MyBaseLLM, ToolCallRecord
from utils.fileio import load
from utils.img import url2img
from utils.translator import Translator


class Request(BaseModel):
    llm: Union[str, MyBaseLLM]
    prompt: Any
    screenshot: list[str] = []
    

class LLMConfig(BaseModel):
    name: str
    sys_prompt: str = ''
    params: dict = {}
    tools: list = []


class StreamCache(BaseModel):
    chunk: str
    full: str


class MyAgent(MyLogger):
    _log_dir: str
    _llm: dict[str, MyBaseLLM]
    __timer: Optional[dict] = None

    def __init__(self,
                 log_key: str = None,
                 llms: Optional[dict[str, LLMConfig]] = None,
                 lang: str = 'zh-hans',
                 ns: str = 'common',
                 agent_id: str = None) -> None:
        self.agent_id = agent_id if agent_id is not None else uuid.uuid4()
        if log_key is None:
            log_key = self.cls_name()
        super().__init__(log_dir=('./logs', log_key))
        if llms is None:
            llms = {}
        self._llm = {}
        for key, llm_config in llms.items():
            self.register_llm(key, llm_config)
        self.translator = Translator(lang, ns)
        self.log('llm.json', {key: llm.name for key, llm in llms.items()})
        self.tool_calls: list[ToolCallRecord] = []
        self.__timer = {}

    @classmethod
    def cls_name(cls) -> str:
        return cls.__name__

    def _timer(self, key: str) -> None:
        t = time.time()
        if key not in self.__timer:
            self.__timer[key] = {'first': t, 'last': t}
        else:
            stat = {
                "t": t,
                "since_first": t - self.__timer[key]['first'],
                "since_last": t - self.__timer[key]['last'],
            }
            self.log(f'timer_{key}.json', stat)
        self.__timer[key]['last'] = t

    def _parse_json(self, json_str: str, default_return: Optional[Union[dict, list]] = None) -> Union[dict, list]:
        if default_return is None:
            default_return = {}
        try:
            return parse_partial_json(json_str)
        except Exception:
            self.log('failed_to_parse_json.txt', json_str)
            return default_return

    def _parse_json_markdown(self, json_str: str, default_return: Optional[Union[dict, list]] = None,
                             verbose_exp: bool = True) -> Union[dict, list]:
        if default_return is None:
            default_return = {}
        try:
            return parse_json_markdown(json_str)
        except Exception:
            if verbose_exp:
                self.log('failed_to_parse_json_md.txt', json_str)
            return default_return

    def _parse_code_markdown(self, s: str) -> list[Code]:
        codes = []
        last_file = 'unknown_file.txt'
        last_block = ''
        state = 'text'
        for line in s.split('\n'):
            if line.strip().startswith('```'):
                if state == 'text':
                    last_block = ''
                    state = 'code'
                else:
                    state = 'text'
                    codes.append(Code(path=last_file, content=last_block.strip()))
                    last_file = 'unknown_file.txt'
            elif state == 'code':
                last_block += '\n' + line
            else:
                for filepath in re.findall(r'\$\((.*)\)', line):
                    last_file = str(filepath)

        return codes

    def __detect_tail_loop(self, text: str, min_pattern: int = 5, max_pattern: int = 30, threshold: int = 4) -> bool:
        
        window_size = max_pattern * (threshold + 1)
        if len(text) < window_size:
            return False

        tail = text[-window_size:]

        for length in range(min_pattern, max_pattern + 1):
            pattern = tail[-length:]
            if pattern.strip() == '':
                continue
            if tail.endswith(pattern * threshold):
                self.log('detect_tail_loop.txt',
                         f'Pattern Length ({min_pattern}~{max_pattern}): {length}\n\n'
                         f'Threshold: {threshold}\n\n'
                         f'Pattern: """\n{pattern}\n"""\n\n'
                         f'Text: """\n{text}\n"""')
                return True  
        return False

    def gen_msg(self, req: Request, history: list[BaseMessage] = []) -> list[BaseMessage]:
        content = []
        if isinstance(req.prompt, str):
            
            if '<|IMAGE|>' in req.prompt:
                prompt_split = req.prompt.split('<|IMAGE|>')
                assert len(prompt_split) == len(req.screenshot) + 1, '图像数量与提示不匹配'
                for index, sub_prompt in enumerate(prompt_split):
                    if sub_prompt.strip():
                        content.append(req.llm.generate_message_block(sub_prompt))
                    if index < len(req.screenshot):
                        content.append(req.llm.generate_message_block(req.screenshot[index]))
                
            
            
            elif '<|TASK|>' in req.prompt:
                prompt_split = req.prompt.split('<|TASK|>')
                for index, sub_prompt in enumerate(prompt_split):
                    if sub_prompt.strip():
                        content.append(req.llm.generate_message_block(sub_prompt))
                    
            else:
                content.append(req.llm.generate_message_block(req.prompt))
            
            content.extend([req.llm.generate_message_block(ss) for ss in req.screenshot])
            
            return [*history, HumanMessage(content=content)]
            
        else:
            
            content_image, content_user, content_assistant = [], [], []
            content_image.extend([req.llm.generate_message_block(ss) for ss in req.screenshot])
            content_user.extend([req.llm.generate_message_block(msg) for msg in req.prompt['user']])
            content_assistant.extend([req.llm.generate_message_block(msg) for msg in req.prompt['assistant']])
            wraped_msg = [
                *history, 
                HumanMessage(content=content_user), 
                AIMessage(content=content_assistant), 
                HumanMessage(content=content_image),
            ]
            return wraped_msg

    def _prepare_request(self, req: Request, cur_retry: int, max_retry: int, suffix: str = None,
                         fallback_model: str = None) -> tuple[str, str]:
        
        if isinstance(req.llm, str):
            req.llm = self._llm[req.llm]

       
        lang_hint = f'\n<language>\n{self.t("ReplyInLang")}\n</language>\n'
        req.llm.set_lang(lang_hint)

        
        if cur_retry >= 3 and fallback_model:
            req.llm = self._replace_model(req.llm, fallback_model)

        
        if suffix is None:
            suffix = inspect.stack()[2][3]  
        try_suffix = '' if cur_retry == 1 else f'-try{cur_retry}-maxtry{max_retry}'
        return suffix, try_suffix

    def _log_prompt(self, name: str, model: str, prompt: Union[str, list[str]]) -> None:
        stat = ResponseManager()
        if isinstance(prompt, str):
            full_prompt = prompt
            stat.delta(full_prompt)
        else:
            full_prompt = ''
            i = 0
            for prompt in prompt:
                if prompt.startswith('data:'):
                    i += 1
                    img = url2img(prompt)
                    file_name = f'image_{i}_{img.width}x{img.height}.png'
                    idx = self.log(file_name, prompt)
                    full_prompt += f'![Image]({idx[0]}.{idx[1]}.{file_name})' + '\n'
                    stat.delta('-' * (img.width // 28) * (img.height // 28))
                else:
                    full_prompt += prompt + '\n'
                    stat.delta(prompt)
        stat.flush()
        self.log(
            f'{name}.md',
            f'`Query Via {model}`\n\n' + full_prompt
        )
        self.log('prompt-stat.json', stat.stat)


    def _log_request(self, req: Request, suffix: str, try_suffix: str) -> None:
        
        self._log_prompt(f'prompt-{suffix}{try_suffix}', req.llm.model_name, req.prompt)
        # for i, image in enumerate(req.screenshot):
        #     self.log(f'screenshot_{i + 1}-{suffix}{try_suffix}.png', image)

    def _invoke(self, req: Request, cur_retry: int = 1, max_retry: int = 5, suffix: str = None,
                fallback_model: str = 'gpt-4o') -> BaseMessage:
        suffix, try_suffix = self._prepare_request(req, cur_retry, max_retry, suffix, fallback_model)
        self._log_request(req, suffix, try_suffix)
        msg = self.gen_msg(req)
        try:
            self._timer(suffix)
            res = req.llm.invoke(msg)
            self.log(f'raw_response-{suffix}{try_suffix}.md', f'`Query Via {req.llm.model_name}`\n\n' + res.content)
            self._timer(suffix)
            return res
        except (HTTPError, ValueError):
            traceback.print_exc()
            print(f'Failed to query using {req.llm.model_name}. Try Times: {cur_retry}.')
        if max_retry == cur_retry:
            raise RetryError(f'Failed to query after {max_retry} attempts. Please see logs in {self.log_dir}.')
        return self._invoke(req, cur_retry=cur_retry + 1, max_retry=max_retry, suffix=suffix)

    def _replace_model(self, llm: MyBaseLLM, tgt_model: str) -> MyBaseLLM:
        return model_factory(
            model=tgt_model,
            sys_msg=llm.sys_msg,
            params=llm.params,
            tools=llm.tools.values(),
            logger=llm.logger,
        )

    def _on_tool_call(self, tool_call: ToolCallRecord) -> None:
        self.log(f'tool_call-{tool_call.name}.json', tool_call.model_dump())
        self.tool_calls.append(tool_call)

    def tool_call_records(self) -> Generator[ToolCallRecord, None, None]:
        while self.tool_calls:
            yield self.tool_calls.pop(0)

    def query(self,
              req: Request,
              cur_retry: int = 1,
              max_retry: int = 5,
              suffix: str = None,
              fallback_model: str = 'gpt-4o',
              ) -> Generator[StreamCache, None, None]:
        suffix, try_suffix = self._prepare_request(req, cur_retry, max_retry, suffix, fallback_model)
        self._log_request(req, suffix, try_suffix)
        msg = self.gen_msg(req)
        res = ''
        need_retry = False
        try:
            self._timer(suffix)
            log_idx = self.log(f'raw_response-{suffix}{try_suffix}.md', f'`Query Via {req.llm.model_name}`\n\n')
            for chunk in req.llm.stream(msg, on_tool_call=self._on_tool_call):
                self.patch_log(log_idx, f'raw_response-{suffix}{try_suffix}.md', chunk.content)
                res += chunk.content
                if (len(res) // 100 != (len(res) - len(chunk.content)) // 100) and self.__detect_tail_loop(res):
                    need_retry = True
                    break
                yield StreamCache(chunk=chunk.content, full=res)
            self.patch_log(log_idx, f'raw_response-{suffix}{try_suffix}.md', '', close=True)
            self._timer(suffix)
        except (HTTPError, ValueError, requests.exceptions.SSLError):
            traceback.print_exc()
            print(f'Failed to query using {req.llm.model_name}. Try Times: {cur_retry}.')
            need_retry = True
        if need_retry:
            if max_retry == cur_retry:
                raise RetryError(f'Failed to query after {max_retry} attempts. Please see logs in {self.log_dir}.')
            for res in self.query(req, cur_retry=cur_retry + 1, max_retry=max_retry, suffix=suffix):
                yield res

    def _load_prompt(self, name: str, params: Optional[dict] = None) -> str:
        filename = inspect.stack()[1].filename
        return load(os.path.join(Path(filename).parent, 'prompts', name), params=params)

    def t(self, key: str, params: Optional[dict[str, Any]] = None, ns: Optional[str] = None) -> str:
        return self.translator.t(key, params, ns)

    def register_llm(self, name: str, config: LLMConfig) -> None:
        self._llm[name] = model_factory(
            config.name,
            config.sys_prompt,
            config.params,
            config.tools,
            self
        )
        if config.sys_prompt:
            self._log_prompt(f'prompt-sys-{name}', config.name, config.sys_prompt)
        else:
            self.log(f'llm_sys_prompt_{name}_empty.md', config.name)


class SubAgent:
    def __init__(self,
                 main_agent: MyAgent,
                 llms: Optional[dict[str, LLMConfig]] = None) -> None:
        self.id = str(uuid.uuid4())
        self.main_agent = main_agent
        if llms is None:
            llms = {}
        llms = {key + self.id: llm for key, llm in llms.items()}
        for key, llm in llms.items():
            self.main_agent.register_llm(key, llm)
        self.log('llm.json', {key: llm.name for key, llm in llms.items()})

    def patch_log(self, *args, **kwargs) -> None:
        self.main_agent.patch_log(*args, **kwargs)

    def log(self, *args, **kwargs) -> list[int]:
        return self.main_agent.log(*args, **kwargs)

    def log_files(self, *args, **kwargs) -> list[int]:
        return self.main_agent.log_files(*args, **kwargs)

    def new_log_cycle(self) -> None:
        self.main_agent.new_log_cycle()

    def t(self, key: str, params: Optional[dict[str, Any]] = None, ns: Optional[str] = None) -> str:
        return self.main_agent.t(key, params, ns)

    def _load_prompt(self, name: str, params: Optional[dict] = None) -> Union[str, list[str]]:
        filename = inspect.stack()[1].filename
        prompt = load(os.path.join(Path(filename).parent, 'prompts', name), params=params)
        prompt_splitter = '<<<split_prompt>>>'
        if prompt_splitter in prompt:
            return prompt.split(f'\n{prompt_splitter}\n')
        return prompt

    def query(self, req: Request, *args, **kwargs) -> Generator[StreamCache, None, None]:
        req.llm += self.id
        yield from self.main_agent.query(req, *args, **kwargs)

    def tool_call_records(self) -> Generator[ToolCallRecord, None, None]:
        yield from self.main_agent.tool_call_records()
