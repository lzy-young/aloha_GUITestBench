import json
import traceback
from typing import Optional
from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk, ToolCall
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_json_schema
from langchain_core.utils.json import parse_partial_json

from core.models.MyBaseLLM import MyBaseLLM, BaseBlock, TextBlock, ToolCallBlock


class MyOpenAILLM(MyBaseLLM):
    def _gen_text_msg(self, text: str) -> dict:
        return {"type": "text", "text": text}

    def _gen_img_msg(self, ss: str) -> dict:
        return {
            "type": "image_url",
            "image_url": {
                "url": ss
            }
        }

    def _gen_payload(self, messages: list[BaseMessage], stream: bool) -> dict:
        payload = {
            **self.params,
            "model": self.model_name,
            "messages": [],
            "stream": stream,
            "tools": self.formatted_tools,
        }
        reformatted_messages = payload['messages']
        sys_msg = []
        if self.lang:
            sys_msg.append(self.lang)
        if isinstance(self.sys_msg, str):
            sys_msg.append(self.sys_msg)
        else:
            sys_msg.extend(self.sys_msg)
        if sys_msg:
            reformatted_messages.append({
                "role": "system",
                "content": [self.generate_message_block(msg) for msg in sys_msg if msg != '']
            })
        for msg in messages:
            re_msg = {"role": self.type2role(msg.type), "content": msg.content}
            if msg.type == 'ai' and msg.tool_calls is not None:
                re_msg['tool_calls'] = [{
                    "id": tool_call["id"],
                    "function": {"arguments": json.dumps(tool_call["args"]), "name": tool_call["name"]},
                    "type": "function"
                } for tool_call in msg.tool_calls]
            if msg.type == 'tool':
                re_msg['tool_call_id'] = msg.tool_call_id
                if isinstance(msg.content, str):
                    content = [msg.content]
                else:
                    content = msg.content
                re_msg['content'] = [self.generate_message_block(block) for block in content]
            reformatted_messages.append(re_msg)
        return payload

    def _convert_tools(self, tools: list[BaseTool]) -> list[dict]:
        tools_schema = []
        for tool in tools:
            
            json_schema = convert_to_json_schema(tool)

            
            tool_schema = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": json_schema.get("properties", {}),
                    "required": json_schema.get("required", [])
                }
            }
            tools_schema.append(tool_schema)
        return tools_schema

    def _build_ai_message_from_generate_result(self, data: dict) -> AIMessage:
        message = AIMessage(
            content=data['choices'][0]['message']['content'],
            usage_metadata={
                "input_tokens": data['usage']['prompt_tokens'],
                "output_tokens": data['usage']['completion_tokens'],
                "total_tokens": data['usage']['total_tokens'],
            },
        )
        if 'tool_calls' in data['choices'][0]['message']:
            for tool_call in data['choices'][0]['message']['tool_calls']:
                tool_name = tool_call['function']['name']
                tool_args = json.loads(tool_call['function']["arguments"])
                message.tool_calls = [
                    ToolCall(name=tool_name,
                             args=tool_args,
                             id=tool_call['id'])
                ]
        return message

    def _pre_handle_stream_chunk(self, chunk: bytes) -> Optional[dict]:
        if not chunk:
            return None
        chunk_text = chunk.decode('utf8', 'ignore')
        if not chunk_text.startswith('data:'):
            return None
        chunk_text = chunk_text[5:].strip()
        if chunk_text == '[DONE]':
            return None
        try:
            return json.loads(chunk_text)
        except Exception:
            traceback.format_exc()
            print(f"Failed to process: {chunk.decode('utf8', 'ignore')}")
            return None

    def _handle_stream_chunk(self, chunk: dict, blocks: list[BaseBlock]) -> Optional[ChatGenerationChunk]:
        if 'choices' not in chunk or len(chunk['choices']) == 0:
            return None
        choice = chunk['choices'][0]
        try:
            if ('finish_reason' in choice
                    and choice['finish_reason'] is not None
                    and choice['finish_reason'] != 'null'):
                if choice['finish_reason'] != 'stop' and choice['finish_reason'] != 'tool_calls':
                    print(f'Unexpected Finish: {choice["finish_reason"]}. Full Response: {chunk}')
                return None

            delta = choice['delta']
            if 'content' in delta and delta['content'] is not None:
                
                content = delta['content'] or ''
                generation_chunk = ChatGenerationChunk(message=AIMessageChunk(content=content))
                if len(blocks) == 0 or blocks[-1].block_type != 'text':
                    blocks.append(TextBlock())
                blocks[-1].block_content += content
                return generation_chunk
            elif 'tool_calls' in delta:
                call = delta['tool_calls'][0]
                if 'id' in call:
                    # start
                    blocks.append(ToolCallBlock(
                        tool_id=call['id'],
                        tool_name=call['function']['name'],
                        kwargs={}
                    ))
                arguments = call['function']['arguments']
                block = blocks[-1]
                if block.block_type == 'tool_use':
                    blocks[-1].block_content += arguments
                    block.kwargs = parse_partial_json(block.block_content or '{}')
                return None
        except Exception:
            traceback.format_exc()
            print(f"Failed to process: {choice}")
            return None
