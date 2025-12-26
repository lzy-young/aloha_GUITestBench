from collections.abc import Callable

import requests
from typing import Any, Optional, Union, Iterator

import curlify
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import BaseMessage, ToolMessage, AIMessage, ToolCall
from langchain_core.outputs import ChatResult, ChatGenerationChunk, ChatGeneration
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from core.logger import MyLogger
from utils.img import url2encoding


class BaseBlock(BaseModel):
    block_type: str
    block_content: str


class TextBlock(BaseBlock):
    block_type: str = 'text'
    block_content: str = ''


class ToolCallBlock(BaseBlock):
    block_type: str = 'tool_use'
    tool_id: str
    tool_name: str
    kwargs: dict
    block_content: str = ''


class StatBlock(BaseBlock):
    block_type: str = 'stat'
    block_content: str = ''
    input_tokens: int
    output_tokens: int


class ToolCallRecord(BaseModel):
    id: str
    name: str
    args: dict
    result: Union[str, list[Union[str, dict]]]


class ToolCallMessage(BaseModel):
    class ToolCallPart(BaseModel):
        type: str = 'tool-call'
        toolCallId: str
        toolName: str
        args: dict

    class TextBlock(BaseModel):
        type: str = 'text'
        text: str

    class MediaBlock(BaseModel):
        type: str = 'media'
        data: str
        mediaType: str = 'image/png'

    class Content(BaseModel):
        type: str = 'content'
        value: list[Union['ToolCallMessage.TextBlock', 'ToolCallMessage.MediaBlock']]

    class ToolResultPart(BaseModel):
        type: str = 'tool-result'
        toolCallId: str
        toolName: str
        output: 'ToolCallMessage.Content'

    call: 'ToolCallMessage.ToolCallPart'
    result: 'ToolCallMessage.ToolResultPart'

    def __init__(self, record: ToolCallRecord) -> None:
        super().__init__(
            call=ToolCallMessage.ToolCallPart(
                toolCallId=record.id,
                toolName=record.name,
                args=record.args,
            ),
            result=ToolCallMessage.ToolResultPart(
                toolCallId=record.id,
                toolName=record.name,
                output=ToolCallMessage.Content(
                    value=[
                        ToolCallMessage.TextBlock(text=str(block)) \
                            if isinstance(block, dict) else \
                            ToolCallMessage.MediaBlock(data=url2encoding(block)) \
                                if block.startswith('data:') else \
                                ToolCallMessage.TextBlock(text=block)
                        for block in (record.result if isinstance(record.result, list) else [record.result])
                    ]
                )
            )
        )


class MyBaseLLM(BaseChatModel):
    type: list[str]
    model_name: str
    endpoint: str
    headers: dict
    sys_msg: Union[str, list[str]]
    params: dict
    proxies: Union[dict, None] = None
    tools: dict[str, BaseTool] = {}
    formatted_tools: list[dict] = []
    logger: Optional[MyLogger] = None
    lang: str = ''

    def _gen_text_msg(self, text: str) -> dict:
        raise NotImplementedError(f'{self.__class__.name}._gen_text_msg must be implemented.')

    def _gen_img_msg(self, ss: str) -> dict:
        raise NotImplementedError(f'{self.__class__.name}._gen_img_msg must be implemented.')

    def _gen_payload(self, messages: list[BaseMessage], stream: bool) -> dict:
        raise NotImplementedError(f'{self.__class__.name}._gen_payload must be implemented.')

    def _build_ai_message_from_generate_result(self, data: dict) -> AIMessage:
        raise NotImplementedError(f'{self.__class__.name}._handle_generate_result must be implemented.')

    def _pre_handle_stream_chunk(self, chunk: bytes) -> Optional[dict]:
        raise NotImplementedError(f'{self.__class__.name}._pre_handle_stream_chunk must be implemented.')

    def _handle_stream_chunk(self, chunk: dict, blocks: list[BaseBlock]) -> Optional[ChatGenerationChunk]:
        raise NotImplementedError(f'{self.__class__.name}._handle_stream_chunk must be implemented.')

    def _convert_tools(self, tools: list[BaseTool]) -> list[dict]:
        raise NotImplementedError(f'{self.__class__.name}._convert_tools must be implemented.')

    def generate_message_block(self, msg: Union[str, dict]) -> dict:
        if isinstance(msg, dict):
            return self._gen_text_msg(str(msg))
        return self._gen_img_msg(msg) if msg.startswith('data:') else self._gen_text_msg(msg)

    def _generate(self,
                  messages: list[BaseMessage],
                  stop: Optional[list[str]] = None,
                  run_manager: Optional[CallbackManagerForLLMRun] = None,
                  **kwargs: Any) -> ChatResult:
        payload = self._gen_payload(messages, stream=False)
        print(f'Use proxy: {self.proxies}')
        response = requests.post(self.endpoint,
                                 headers=self.headers,
                                 json=payload,
                                 proxies=self.proxies,
                                 timeout=300)
        self.logger.log('curl_cmd.txt', curlify.to_curl(response.request))
        response.raise_for_status()
        data = response.json()

        ai_message = self._build_ai_message_from_generate_result(data)
        tool_messages = self._run_tools(ai_message.tool_calls)
        if tool_messages:
            messages.append(ai_message)
            messages.extend(tool_messages)
            res = self._generate(messages, stop, run_manager, **kwargs)
            return ChatResult(generations=[ChatGeneration(message=ai_message), *res.generations])
        else:
            return ChatResult(generations=[ChatGeneration(message=ai_message)])

    def _build_ai_message_from_stream_blocks(self, data: list[BaseBlock]) -> AIMessage:
        ai_message = AIMessage(content='',
                               usage_metadata={
                                   "input_tokens": 0,
                                   "output_tokens": 0,
                                   "total_tokens": 0,
                               })
        for block in data:
            if block.block_type == 'text':
                ai_message.content += block.block_content
            elif block.block_type == 'stat':
                ai_message.usage_metadata['input_tokens'] += block.input_tokens
                ai_message.usage_metadata['output_tokens'] += block.output_tokens
                ai_message.usage_metadata['total_tokens'] += block.input_tokens + block.output_tokens
            elif block.block_type == 'tool_use':
                ai_message.tool_calls.append({
                    'id': block.tool_id,
                    'name': block.tool_name,
                    'args': block.kwargs,
                })
        return ai_message

    def _stream(self,
                messages: list[BaseMessage],
                stop: Optional[list[str]] = None,
                run_manager: Optional[CallbackManagerForLLMRun] = None,
                on_tool_call: Optional[Callable[[ToolCallRecord], None]] = None,
                **kwargs: Any,
                ) -> Iterator[ChatGenerationChunk]:
        content_blocks: list[BaseBlock] = []
        payload = self._gen_payload(messages, stream=True)
        with requests.post(self.endpoint,
                           headers=self.headers,
                           json=payload,
                           proxies=self.proxies,
                           timeout=3000,
                           stream=True) as response:
            self.logger.log('curl_cmd.txt', curlify.to_curl(response.request))
            response.raise_for_status()
            for chunk in response.iter_lines():
                chunk = self._pre_handle_stream_chunk(chunk)
                if chunk is None:
                    continue
                chunk = self._handle_stream_chunk(chunk, content_blocks)
                if chunk is None:
                    continue
                yield chunk

        ai_message = self._build_ai_message_from_stream_blocks(content_blocks)
        tool_messages = self._run_tools(ai_message.tool_calls)
        if tool_messages:
            messages.append(ai_message)
            messages.extend(tool_messages)
            if on_tool_call:
                for i, tool_call in enumerate(ai_message.tool_calls):
                    on_tool_call(ToolCallRecord(
                        id=tool_call['id'],
                        name=tool_call['name'],
                        args=tool_call['args'],
                        result=tool_messages[i].content
                    ))
            yield from self._stream(messages, stop, run_manager, on_tool_call=on_tool_call, **kwargs)

    def _call_tool(self,
                   tool_call: ToolCall) -> Union[str, list[str]]:
        if tool_call['name'] not in self.tools:
            return f'Tool {tool_call["name"]} does not exist.'
        tool = self.tools[tool_call['name']]
        tool_call_result = tool.invoke(input=tool_call['args'])
        return tool_call_result

    def _run_tools(self, tool_calls: list[ToolCall]) -> list[ToolMessage]:
        return [
            ToolMessage(content=self._call_tool(tool_call), tool_call_id=tool_call['id'])
            for tool_call in tool_calls
        ]

    @property
    def _llm_type(self) -> str:
        return self.model_name

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name}

    def bind_tools(self,
                   tools: list[BaseTool],
                   **kwargs: Any,
                   ) -> Runnable[LanguageModelInput, BaseMessage]:
        
        self.formatted_tools = self._convert_tools(tools)
        self.tools = {tool.name: tool for tool in tools}
        return self

    @staticmethod
    def type2role(msg_type: str) -> str:
        return {
            "human": "user",
            "ai": "assistant",
            "system": "system",
            "tool": "tool",
        }[msg_type]

    def set_lang(self, lang: str) -> None:
        self.lang = lang
